import os
import logging
import traceback
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.limiter import RateLimitMiddleware
from app.core.logging_config import setup_logging, request_id_var
from app.api.v1.middleware import ASGIRequestIDMiddleware

# Initialize JSON logging system
setup_logging()
logger = logging.getLogger("app.main")
error_file_logger = logging.getLogger("system_errors")

# Configure file logging for untrusted/unhandled exceptions
try:
    file_handler = logging.FileHandler("system_error.log")
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
    ))
    error_file_logger.addHandler(file_handler)
    error_file_logger.setLevel(logging.ERROR)
except Exception as e:
    logger.error(f"Failed to setup system_error.log file handler: {str(e)}")

app = FastAPI(
    title="AI-powered CV Management & Grading System API",
    description="Backend API for managing, parsing, and grading CVs using Google Gemini AI.",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add ASGIRequestIDMiddleware for tracing request flows
app.add_middleware(ASGIRequestIDMiddleware)

# Add Rate Limiting Middleware
app.add_middleware(RateLimitMiddleware)

# Include API v1 routes
app.include_router(api_router, prefix="/api/v1")

# Jinja2 template engine — handles its own template caching internally
templates = Jinja2Templates(directory="templates")

@app.get("/evaluate", response_class=HTMLResponse, tags=["Frontend"])
def get_evaluate_page(request: Request):
    return templates.TemplateResponse(request=request, name="evaluate.html", context={})

@app.get("/portfolio-builder", response_class=HTMLResponse, tags=["Frontend"])
def get_portfolio_builder_page(request: Request):
    return templates.TemplateResponse(request=request, name="portfolio_builder.html", context={})



@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = request_id_var.get()
    tb = traceback.format_exc()
    
    # Write full traceback to system_error.log
    error_file_logger.error(
        f"Unhandled exception during {request.method} {request.url.path} [Request ID: {request_id}]: {str(exc)}\nTraceback:\n{tb}"
    )
    
    # Log to JSON logger (stdout)
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "request_id": request_id
        }
    )

@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "AI CV Management API",
        "version": "1.0.0"
    }


# ─── APScheduler Background Cleanup Job ───────────────────────────────────────
from apscheduler.schedulers.background import BackgroundScheduler
from app.core.database import get_supabase_admin

def cleanup_stale_sessions():
    """APScheduler task: monthly clean up of stale chatbot sessions (>30 days old)"""
    logger.info("Running monthly cleanup task for stale chatbot sessions...")
    try:
        supabase = get_supabase_admin()
        supabase.rpc("cleanup_chatbot_sessions").execute()
        logger.info("Successfully cleaned up stale chatbot sessions.")
    except Exception as e:
        logger.error(f"Error during monthly stale chatbot sessions cleanup: {e}")

# Scheduler setup
scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    # Schedule cleanup task to run at 00:00 on the first day of each month
    scheduler.add_job(
        cleanup_stale_sessions, 
        'cron', 
        day=1, 
        hour=0, 
        minute=0, 
        id="monthly_session_cleanup"
    )
    scheduler.start()
    logger.info("APScheduler initialized and started successfully.")

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()
    logger.info("APScheduler shut down successfully.")
