import os
import json
import time
import asyncio
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 60  # max requests per window
LIMITER_FILE = "/tmp/limiter_data.json"

# Lock to ensure thread-safe/asyncio-safe file operations in a single process
file_lock = asyncio.Lock()

def _read_limiter_data() -> dict:
    if not os.path.exists(LIMITER_FILE):
        return {}
    try:
        with open(LIMITER_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _write_limiter_data(data: dict):
    # Ensure parent directories exist
    os.makedirs(os.path.dirname(LIMITER_FILE), exist_ok=True)
    with open(LIMITER_FILE, "w") as f:
        json.dump(data, f)

async def check_rate_limit(client_ip: str) -> bool:
    """
    Checks if a client has exceeded the rate limit.
    Returns True if allowed, False if rate limited.
    """
    async with file_lock:
        # Run synchronous file I/O in a separate thread pool to prevent blocking the event loop
        data = await asyncio.to_thread(_read_limiter_data)
        
        current_time = time.time()
        client_data = data.get(client_ip)
        
        if not client_data:
            data[client_ip] = {
                "count": 1,
                "reset_time": current_time + RATE_LIMIT_WINDOW
            }
            allowed = True
        else:
            reset_time = client_data.get("reset_time", 0)
            count = client_data.get("count", 0)
            
            if current_time > reset_time:
                # Window expired, reset counter and window
                data[client_ip] = {
                    "count": 1,
                    "reset_time": current_time + RATE_LIMIT_WINDOW
                }
                allowed = True
            else:
                if count >= RATE_LIMIT_MAX_REQUESTS:
                    allowed = False
                else:
                    client_data["count"] = count + 1
                    allowed = True
                    
        await asyncio.to_thread(_write_limiter_data, data)
        return allowed

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Retrieve client IP or default to unknown
        client_ip = request.client.host if request.client else "unknown"
        
        # Bypass rate limiting for health check, API docs and schema endpoints
        if request.url.path in ["/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
            
        allowed = await check_rate_limit(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too Many Requests. Rate limit exceeded."}
            )
            
        return await call_next(request)
