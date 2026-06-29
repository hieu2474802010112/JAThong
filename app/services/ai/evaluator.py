import json
from fastapi import HTTPException, status
from langchain_core.messages import SystemMessage, HumanMessage
from app.models.evaluation import CVEvaluationResult
from app.services.ai.prompt_templates import SYSTEM_PROMPT
from app.services.ai.utils import get_gemini_llm

async def evaluate_cv(parsed_text: str) -> CVEvaluationResult:
    try:
        # Use common helper with fallback
        llm = get_gemini_llm(temperature=0.0)
        
        # Force structured output conforming to the Pydantic schema
        structured_llm = llm.with_structured_output(CVEvaluationResult)
        
        # Formulate system and human messages
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
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
