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
import hashlib
import json

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
r = None
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

@celery_app.task(bind=True, max_retries=10, default_retry_delay=5)
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
        evaluation_result_dict = None
        cache_key = None
        if r is not None:
            try:
                parsed_text_hash = hashlib.sha256(parsed_text.encode('utf-8')).hexdigest()
                cache_key = f"cv_eval_cache_v2:{parsed_text_hash}"
                lock_key = f"cv_eval_lock:{parsed_text_hash}"
                
                cached_data = r.get(cache_key)
                if cached_data:
                    logger.info(f"L2 Cache Hit for CV {cv_id}! Bypassing AI evaluation.")
                    evaluation_result_dict = json.loads(cached_data)
                else:
                    # Race Condition Prevention (Cache Stampede)
                    # If multiple workers try to evaluate the same CV at the exact same time,
                    # only the first one should call AI. The others should wait.
                    acquired = r.setnx(lock_key, "locked")
                    if acquired:
                        r.expire(lock_key, 60) # 60s lock
                    else:
                        raise Exception("Đang có người chấm CV này rồi, bạn phải chờ đợi trong giây lát!")
            except Exception as cache_err:
                if "Đang có người chấm CV này rồi" in str(cache_err):
                    raise cache_err # Bubble up to trigger Celery retry
                logger.warning(f"Redis L2 Cache read error: {cache_err}")

        if not evaluation_result_dict:
            logger.info(f"Invoking AI evaluator for CV {cv_id}...")
            evaluation_result = run_async_sync(evaluate_cv(parsed_text))
            evaluation_result_dict = evaluation_result.model_dump()
            
            if cache_key and r is not None:
                try:
                    r.setex(cache_key, 30 * 24 * 3600, json.dumps(evaluation_result_dict))
                except Exception as cache_err:
                    logger.warning(f"Redis L2 Cache write error: {cache_err}")
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
            "evaluation_result": evaluation_result_dict
        }
        supabase.table("cv_records").update(update_data).eq("id", cv_id).execute()
        logger.info(f"Successfully evaluated CV {cv_id}")
        return evaluation_result_dict
    except Exception as e:
        logger.error(f"Database error while saving results for CV {cv_id}: {str(e)}")
        supabase.table("cv_records").update({"status": "failed"}).eq("id", cv_id).execute()
        raise e
