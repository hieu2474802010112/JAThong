import json
from fastapi import HTTPException, status
from cachetools import TTLCache
from langchain_core.messages import SystemMessage, HumanMessage
from app.models.evaluation import CVEvaluationResult
from app.services.ai.prompt_templates import SECURITY_PROTOCOL
from app.services.ai.utils import get_gemini_llm
from app.core.database import get_supabase_admin

# Cache configuration for dynamic criteria
criteria_cache = TTLCache(maxsize=10, ttl=86400)  # TTL of 24 hours

def get_dynamic_criteria() -> str:
    cache_key = "default_cv_rubric"
    if cache_key in criteria_cache:
        return criteria_cache[cache_key]
        
    try:
        supabase = get_supabase_admin()
        res = supabase.table("evaluation_settings").select("criteria_text").eq("setting_key", cache_key).execute()
        if res.data:
            criteria = res.data[0].get("criteria_text")
            if criteria:
                criteria_cache[cache_key] = criteria
                return criteria
    except Exception:
        # Graceful fallback in case table doesn't exist or DB connection error
        pass
        
    default_criteria = (
        "ANALYSIS GUIDELINES:\n"
        "- Extract candidate's personal details (Name, Contact, Email, Socials).\n"
        "- Extract work experience, education, skills, and projects.\n"
        "- Evaluate the candidate based on predefined rubrics.\n"
        "- Output strictly clean JSON conforming to the requested schema. No conversational filler, markdown formatting, or preamble outside the JSON block."
    )
    return default_criteria

def clear_criteria_cache():
    criteria_cache.clear()

async def evaluate_cv(parsed_text: str) -> CVEvaluationResult:
    try:
        # Use common helper with fallback
        llm = get_gemini_llm(temperature=0.0)
        
        # Force structured output conforming to the Pydantic schema
        structured_llm = llm.with_structured_output(CVEvaluationResult)
        
        # Combine hardcoded security protocol with dynamic rubrics criteria
        system_prompt = f"{SECURITY_PROTOCOL}\n\n{get_dynamic_criteria()}"
        
        # Formulate system and human messages
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Please analyze and evaluate this CV content:\n\n{parsed_text}")
        ]
        
        # Async invoke to prevent blocking FastAPI event loop
        result = await structured_llm.ainvoke(messages)
        
        if not result or not isinstance(result, CVEvaluationResult):
            raise ValueError("AI response did not match the expected structured format.")
            
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gemini AI Evaluation failed or returned invalid JSON format: {str(e)}"
        )
