import os
import time
import asyncio
import redis
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 60  # max requests per window

# Initialize connection pool and redis client
redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
redis_client = redis.Redis(connection_pool=redis_pool)

def _check_rate_limit_redis(client_ip: str) -> bool:
    key = f"rate_limit:{client_ip}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = pipe.execute()
        
        current_requests = results[0]
        ttl = results[1]
        
        if ttl == -1 or current_requests == 1:
            redis_client.expire(key, RATE_LIMIT_WINDOW)
            
        if current_requests > RATE_LIMIT_MAX_REQUESTS:
            return False
        return True
    except Exception:
        # Fail-open strategy: allow requests if redis is down
        return True

async def check_rate_limit(client_ip: str) -> bool:
    """
    Checks if a client has exceeded the rate limit using Redis.
    Returns True if allowed, False if rate limited.
    """
    return await asyncio.to_thread(_check_rate_limit_redis, client_ip)

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only apply rate limiting to backend API endpoints
        if not (request.url.path.startswith("/api/v1/") or request.url.path.startswith("/api/")):
            return await call_next(request)

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

