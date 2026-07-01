import asyncio
import logging
import traceback
from celery import Celery
from celery.signals import task_prerun, task_postrun
from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.ai.evaluator import evaluate_cv
from app.core.logging_config import request_id_var

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    "cv_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Celery signals to propagate request_id
@task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **info):
    headers = task.request.headers or {}
    request_id = headers.get("request_id", "-")
    task.request_id_token = request_id_var.set(request_id)

@task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, state, **info):
    token = getattr(task, "request_id_token", None)
    if token:
        request_id_var.reset(token)

@celery_app.task(bind=True, max_retries=3, retry_backoff=True)
def evaluate_cv_task(self, cv_id: str):
    logger.info(f"Starting Celery task to evaluate CV {cv_id}")
    supabase = get_supabase_admin()
    
    try:
        # 1. Fetch CV record from database
        res = supabase.table("cv_records").select("parsed_text").eq("id", cv_id).execute()
        if not res.data:
            raise ValueError(f"CV record with ID {cv_id} not found.")
        
        parsed_text = res.data[0].get("parsed_text")
        if not parsed_text:
            raise ValueError("CV parsed text is empty.")
        
        # 2. Call AI evaluator (async)
        logger.info(f"Invoking AI evaluator for CV {cv_id}...")
        evaluation_result = asyncio.run(evaluate_cv(parsed_text))
        
        # 3. Save results back to database
        update_data = {
            "status": "evaluated",
            "evaluation_result": evaluation_result.model_dump()
        }
        supabase.table("cv_records").update(update_data).eq("id", cv_id).execute()
        logger.info(f"Successfully evaluated CV {cv_id}")
        return evaluation_result.model_dump()
        
    except Exception as e:
        # Check if we exceeded max_retries (Note: self.request.retries is 0-indexed)
        if self.request.retries >= self.max_retries:
            logger.error(f"Task failed after reaching max retries ({self.max_retries}) for CV {cv_id}. Storing error log in database.")
            try:
                # Store failure log into public.ai_evaluations
                tb = traceback.format_exc()
                error_data = {
                    "cv_record_id": cv_id,
                    "overall_score": None,
                    "error_log": f"Task failed after {self.max_retries} retries.\nException: {str(e)}\n\nTraceback:\n{tb}"
                }
                # Remove existing evaluation if any, and insert new error record
                supabase.table("ai_evaluations").delete().eq("cv_record_id", cv_id).execute()
                supabase.table("ai_evaluations").insert(error_data).execute()
                
                # Update status of cv_records to failed
                supabase.table("cv_records").update({"status": "failed"}).eq("id", cv_id).execute()
            except Exception as db_err:
                logger.error(f"Failed to record failure state in database for CV {cv_id}: {str(db_err)}")
            raise e
        else:
            logger.warning(f"Error evaluating CV {cv_id}. Retrying... (Attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e)
