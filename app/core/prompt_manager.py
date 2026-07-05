import os
import logging

logger = logging.getLogger("prompt_manager")

_SYSTEM_PROMPT_CACHE = None

def get_system_prompt() -> str:
    """
    Loads the system instruction prompt file from disk on the first call,
    caching it in memory. Subsequent calls return the cached text from RAM.
    """
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE
        
    prompt_version = os.environ.get("PROMPT_VERSION", "cv_evaluator_v1.txt")
    
    # Check possible paths relative to application runtime directory
    possible_paths = [
        os.path.join(os.getcwd(), "prompts", prompt_version),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "prompts", prompt_version),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", prompt_version),
        os.path.join(os.getcwd(), prompt_version),
        prompt_version
    ]
    
    loaded_text = ""
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded_text = f.read()
                logger.info(f"Loaded prompt version {prompt_version} successfully from path: {path}")
                break
            except Exception as e:
                logger.error(f"Error reading prompt file at {path}: {e}")
                
    if not loaded_text:
        # Fallback default prompt if file cannot be found/read
        logger.warning(f"Could not load prompt file '{prompt_version}' from disk. Using fallback default instructions.")
        loaded_text = (
            "You are JATHONG CV Score AI (Version: V1.0) — Hệ thống AI chuyên nghiệp phân tích, chấm điểm và gợi ý cải thiện CV.\n"
            "Nhiệm vụ: Chấm điểm CV theo 15 tiêu chí độc lập (thang 0-10), tính điểm trung bình, chỉ ra điểm mạnh/yếu và đề xuất cải thiện."
        )
        
    _SYSTEM_PROMPT_CACHE = loaded_text
    return _SYSTEM_PROMPT_CACHE
