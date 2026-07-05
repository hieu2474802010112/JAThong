import asyncio
import concurrent.futures
import logging
import traceback
from celery import Celery
from celery.signals import task_prerun, task_postrun
from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.ai.evaluator import evaluate_cv
from app.core.logging_config import request_id_var

def run_async_sync(coro):
    """Runs a coroutine synchronously, safely handling existing running event loops."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)

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
    result_expires=1800,              # 30-minute expiration to prevent Redis memory bloat
    worker_prefetch_multiplier=1,     # Forces fair round-robin scheduling among workers
    task_soft_time_limit=120,         # Soft limit: raises SoftTimeLimitExceeded after 120 s
    task_time_limit=150,              # Hard limit: kills worker process after 150 s
)

# Detect if Redis is available, fallback to eager mode if not
try:
    import redis
    r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=1.0, socket_connect_timeout=1.0)
    r.ping()
    logger.info("Successfully connected to Redis. Celery is running in Celery worker mode.")
except Exception as e:
    logger.warning(f"Redis is not available at {settings.REDIS_URL}: {e}. Celery task execution is set to EAGER mode (sync).")
    celery_app.conf.task_always_eager = True

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

@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def evaluate_cv_task(self, cv_id: str):
    logger.info(f"Starting Celery task to evaluate CV {cv_id}")
    supabase = get_supabase_admin()
    
    # 1. Fetch CV record from database
    try:
        res = supabase.table("cv_records").select("parsed_text").eq("id", cv_id).execute()
        if not res.data:
            raise ValueError(f"CV record with ID {cv_id} not found.")
        
        parsed_text = res.data[0].get("parsed_text")
        if not parsed_text:
            raise ValueError("CV parsed text is empty.")
    except Exception as e:
        logger.error(f"Database error while fetching CV {cv_id}: {str(e)}")
        # Database fetch issues fail immediately to prevent infinite retries on invalid records
        supabase.table("cv_records").update({"status": "failed"}).eq("id", cv_id).execute()
        raise e

    # 2. Call AI evaluator (async) with Celery auto-retry on API errors
    try:
        logger.info(f"Invoking AI evaluator for CV {cv_id}...")
        evaluation_result = run_async_sync(evaluate_cv(parsed_text))
    except Exception as api_err:
        # If it is classified as not a CV, do not retry
        if isinstance(api_err, ValueError) and "không phải là một CV hợp lệ" in str(api_err):
            logger.error(f"Validation failed for CV {cv_id}: {str(api_err)}")
            try:
                error_data = {
                    "cv_record_id": cv_id,
                    "overall_score": 0,
                    "error_log": str(api_err)
                }
                supabase.table("ai_evaluations").delete().eq("cv_record_id", cv_id).execute()
                supabase.table("ai_evaluations").insert(error_data).execute()
                supabase.table("cv_records").update({"status": "failed"}).eq("id", cv_id).execute()
            except Exception as db_err:
                logger.error(f"Failed to record validation failure for CV {cv_id}: {str(db_err)}")
            raise api_err

        logger.warning(f"Gemini API call failed for CV {cv_id}. Retrying... (Attempt {self.request.retries + 1}/{self.max_retries})")
        try:
            raise self.retry(exc=api_err)
        except Exception as retry_exc:
            if self.request.retries >= self.max_retries:
                logger.error(f"Task failed after reaching max retries ({self.max_retries}) for CV {cv_id}. Storing error log in database.")
                try:
                    tb = traceback.format_exc()
                    error_data = {
                        "cv_record_id": cv_id,
                        "overall_score": None,
                        "error_log": f"Task failed after {self.max_retries} retries.\nException: {str(api_err)}\n\nTraceback:\n{tb}"
                    }
                    supabase.table("ai_evaluations").delete().eq("cv_record_id", cv_id).execute()
                    supabase.table("ai_evaluations").insert(error_data).execute()
                    supabase.table("cv_records").update({"status": "failed"}).eq("id", cv_id).execute()
                except Exception as db_err:
                    logger.error(f"Failed to record failure state in database for CV {cv_id}: {str(db_err)}")
            raise retry_exc

    # 3. Save results back to database
    try:
        update_data = {
            "status": "evaluated",
            "evaluation_result": evaluation_result.model_dump()
        }
        supabase.table("cv_records").update(update_data).eq("id", cv_id).execute()
        logger.info(f"Successfully evaluated CV {cv_id}")
        return evaluation_result.model_dump()
    except Exception as e:
        logger.error(f"Database error while saving results for CV {cv_id}: {str(e)}")
        supabase.table("cv_records").update({"status": "failed"}).eq("id", cv_id).execute()
        raise e
