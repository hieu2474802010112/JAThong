import os
import logging
import redis
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis L2 cache for active model
try:
    _redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception:
    _redis_client = None

_working_model_cache = None

def get_working_model_cache() -> str | None:
    global _working_model_cache
    if _redis_client:
        try:
            val = _redis_client.get("working_gemini_model")
            if val:
                return val
        except Exception:
            pass
    return _working_model_cache

def set_working_model_cache(model_name: str):
    global _working_model_cache
    _working_model_cache = model_name
    if _redis_client:
        try:
            _redis_client.set("working_gemini_model", model_name)
        except Exception:
            pass

def get_gemini_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    # Allow overriding preferred model via GEMINI_MODEL env var without editing code (solves Point 5)
    preferred_model = os.environ.get("GEMINI_MODEL")
    models = []
    if preferred_model:
        models.append(preferred_model)
        
    models.extend([
        "gemini-3.5-flash",
        "gemini-3.1-pro-preview",
    ])
    
    # Try the cached model directly without pinging if available
    cached_model = get_working_model_cache()
    if cached_model and cached_model in models:
        try:
            return ChatGoogleGenerativeAI(
                model=cached_model,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
                max_retries=0
            )
        except Exception:
            pass
            
    for model_name in models:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
                max_retries=0
            )
            # Test connectivity using a fast ping message
            llm.invoke("ping")
            set_working_model_cache(model_name)
            logger.info(f"Connected to Model {model_name}")
            return llm
        except Exception as e:
            logger.warning(f"Model {model_name} failed, trying next... Error: {str(e)}")
            
    raise RuntimeError("All configured Gemini models failed to initialize.")
