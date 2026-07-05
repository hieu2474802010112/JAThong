from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.ai.chatbot import chat_with_candidate
from app.services.ai.scorer import clear_criteria_cache
from app.core.database import get_supabase_admin

router = APIRouter()

class CandidateChatRequest(BaseModel):
    message: str
    session_id: str

class CandidateSessionRequest(BaseModel):
    cv_record_id: str


@router.post("/session")
async def init_chat_session(request: CandidateSessionRequest):
    """
    Create or retrieve a chat session for a given cv_record_id.
    Returns session_id and the full message history so the frontend
    can display prior conversation turns.
    """
    supabase = get_supabase_admin()
    try:
        # Try to find an existing session for this cv_record_id
        res = supabase.table("chat_sessions") \
            .select("id") \
            .eq("cv_record_id", request.cv_record_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        if res.data:
            session_id = res.data[0]["id"]
        else:
            # Create a new session linked to the cv_record
            insert_res = supabase.table("chat_sessions").insert({
                "cv_record_id": request.cv_record_id
            }).execute()
            session_id = insert_res.data[0]["id"]

        # Load message history for this session
        history_res = supabase.table("chat_messages") \
            .select("sender", "content", "created_at") \
            .eq("session_id", session_id) \
            .order("created_at", desc=False) \
            .execute()

        return {
            "session_id": session_id,
            "history": history_res.data or []
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize chat session: {str(e)}"
        )


@router.post("/candidate")
async def candidate_chat(request: CandidateChatRequest):
    reply = await chat_with_candidate(message=request.message, session_id=request.session_id)
    return {"reply": reply}


@router.post("/clear-criteria-cache")
async def clear_criteria_cache_endpoint():
    """Internal utility: clears rubric cache so updated criteria take effect immediately."""
    clear_criteria_cache()
    return {"status": "Cache cleared successfully"}
