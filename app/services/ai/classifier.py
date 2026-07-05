"""
classifier.py — CV Document Validation
----------------------------------------
Responsible for checking whether an uploaded document is a valid CV/Resume
before passing it to the evaluation pipeline.

Public API:
  - check_is_cv(parsed_text: str) -> bool
"""
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.ai.utils import get_gemini_llm

# Common CV keywords for fast heuristic pre-check (avoid wasting Gemini API calls)
_CV_KEYWORDS = [
    # English
    "education", "experience", "skills", "projects", "awards", "languages",
    "certificates", "profile", "objective", "contact", "resume", "curriculum vitae",
    "intern", "freelance",
    # Vietnamese
    "học vấn", "kinh nghiệm", "kỹ năng", "dự án", "giải thưởng", "ngôn ngữ",
    "chứng chỉ", "thành tích", "mục tiêu", "liên hệ", "hoạt động", "tuyển dụng",
    "thực tập", "cv",
]

async def check_is_cv(parsed_text: str) -> bool:
    """
    Fast two-stage classification to confirm the document is a CV/Resume.

    Stage 1 — Heuristic (fast-path):
        Count keyword matches. If >= 3 CV-related keywords found, treat as CV
        and skip Gemini API call to conserve quota and reduce latency.

    Stage 2 — LLM Verification (only when heuristic is inconclusive):
        Invoke Gemini with a concise YES/NO prompt on first 2000 chars.
        Falls back to True on API errors so legitimate CVs are not blocked.
    """
    if not parsed_text or len(parsed_text.strip()) < 100:
        return False

    # Stage 1: fast heuristic
    text_lower = parsed_text.lower()
    matches = sum(1 for kw in _CV_KEYWORDS if kw in text_lower)
    if matches >= 3:
        return True

    # Stage 2: LLM fallback
    try:
        llm = get_gemini_llm(temperature=0.0)
        messages = [
            SystemMessage(content=(
                "You are an expert HR assistant. Classify if the given text is a "
                "candidate's CV/Resume (Curriculum Vitae).\n"
                "A CV typically contains personal info, education, skills, work "
                "experience, projects, or achievements.\n"
                "If the text is a cookbook, essay, news article, spam, manual, "
                "story, or completely unrelated to a person's profile, reply 'NO'.\n"
                "Reply with exactly 'YES' or 'NO'."
            )),
            HumanMessage(content=f"Text to classify:\n\n{parsed_text[:2000]}")
        ]
        response = await llm.ainvoke(messages)
        content = response.content

        # Normalise content (can be str or list of parts)
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
                elif hasattr(part, "text"):
                    parts.append(getattr(part, "text", ""))
            content = " ".join(parts)

        return "YES" in str(content).strip().upper()
    except Exception:
        # Fail open: do not block valid CVs on transient API errors
        return True
