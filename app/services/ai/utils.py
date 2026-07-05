import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings

logger = logging.getLogger(__name__)

_working_model_cache = None

def set_working_model_cache(model_name: str):
    global _working_model_cache
    _working_model_cache = model_name

def get_gemini_llm(temperature: float = 0.7) -> ChatGoogleGenerativeAI:
    global _working_model_cache
    # Allow overriding preferred model via GEMINI_MODEL env var without editing code (solves Point 5)
    preferred_model = os.environ.get("GEMINI_MODEL")
    models = []
    if preferred_model:
        models.append(preferred_model)
        
    models.extend([
        "gemini-3.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-1.0-pro",
        "gemini-pro"
    ])
    
    # Try the cached model directly without pinging if available
    if _working_model_cache and _working_model_cache in models:
        try:
            return ChatGoogleGenerativeAI(
                model=_working_model_cache,
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
            _working_model_cache = model_name
            logger.info(f"Connected to Model {model_name}")
            return llm
        except Exception as e:
            logger.warning(f"Model {model_name} failed, trying next... Error: {str(e)}")
            
    raise RuntimeError("All configured Gemini models failed to initialize.")
