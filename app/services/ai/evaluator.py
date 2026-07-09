"""
evaluator.py — Gemini AI Orchestration
----------------------------------------
Entry point for CV evaluation. Calls check_is_cv() to validate the document,
then invokes Gemini with structured output, then delegates score calibration
to calculate_final_score() in scorer.py.

Public API:
  - evaluate_cv(parsed_text: str) -> CVEvaluationResult
"""
import os
import logging
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.models.evaluation import CVEvaluationResult
from app.services.ai.prompt_templates import SECURITY_PROTOCOL
from app.services.ai.utils import get_gemini_llm
import app.services.ai.utils as ai_utils
from app.services.ai.classifier import check_is_cv
from app.services.ai.scorer import clean_text, get_dynamic_criteria, calculate_final_score
from app.core.config import settings
from app.core.prompt_manager import get_system_prompt

# Ordered list of Gemini models to try (most capable first, legacy last).
# The first model that succeeds is cached in-process for subsequent requests.
_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
]


async def evaluate_cv(parsed_text: str) -> CVEvaluationResult:
    """
    Full CV evaluation pipeline:
      1. Validate document is a CV (fast heuristic + optional Gemini check)
      2. Clean / normalise text
      3. Build system prompt (static rubric + dynamic DB overrides)
      4. Invoke Gemini with structured output (retries across fallback models)
      5. Calibrate score with Python business rules (scorer.py)

    Raises:
      ValueError: if the document is not a valid CV
      HTTPException 500: if all Gemini model invocations fail
    """
    # ── 1. CV validation ──────────────────────────────────────────────
    if not await check_is_cv(parsed_text):
        raise ValueError("Tài liệu tải lên không phải là một CV hợp lệ. Vui lòng kiểm tra lại.")

    # ── 2. Text normalisation ─────────────────────────────────────────
    cleaned_text = clean_text(parsed_text)

    # ── 3. Build prompt ───────────────────────────────────────────────
    db_rubric = get_dynamic_criteria()
    system_prompt = f"{SECURITY_PROTOCOL}\n\n{get_system_prompt()}"
    if db_rubric:
        system_prompt += f"\n\n[DYNAMIC EVALUATION CRITERIA & SCORING RULES]\n{db_rubric}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Please analyze and evaluate this CV content:\n\n{cleaned_text}"),
    ]

    # ── 4. Gemini invocation with model fallback ───────────────────────
    # Prioritise the last model that worked (cached across requests)
    models = list(_FALLBACK_MODELS)
    preferred = os.environ.get("GEMINI_MODEL") or ai_utils.get_working_model_cache()
    if preferred and preferred in models:
        models.remove(preferred)
        models.insert(0, preferred)
    elif preferred:
        models.insert(0, preferred)

    last_error: Exception | None = None
    for model_name in models:
        try:
            logger.info(f"Evaluating CV with model: {model_name}...")
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.0,
                max_retries=0,        # We handle retries ourselves via fallback list
                request_timeout=60,   # 60-second hard timeout per model attempt
            )
            structured_llm = llm.with_structured_output(CVEvaluationResult)
            result = await structured_llm.ainvoke(messages)

            if not isinstance(result, CVEvaluationResult):
                raise ValueError("AI response did not match the expected structured format.")

            # ── 5. Score calibration ──────────────────────────────────
            result.score = calculate_final_score(result, cleaned_text)
            ai_utils.set_working_model_cache(model_name)
            logger.info(f"Successfully evaluated CV with model {model_name}. Final Score: {result.score}")
            return result

        except Exception as exc:
            logger.warning(f"Model {model_name} failed: {str(exc)}")
            last_error = exc
            continue

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Gemini AI Evaluation failed on all fallback models. Last error: {str(last_error)}",
    )
