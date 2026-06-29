from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from app.services.ai.chatbot import chat_with_candidate, chat_with_hr
from app.core.database import get_supabase_admin

router = APIRouter()

class CandidateChatRequest(BaseModel):
    message: str
    session_id: str

class HRChatRequest(BaseModel):
    query: str

async def verify_admin_token(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'."
        )
    token = authorization.split(" ")[1]
    
    supabase = get_supabase_admin()
    try:
        user_res = supabase.auth.get_user(token)
        user = user_res.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token or user not found."
            )
        
        role_res = supabase.table("users").select("role").eq("id", user.id).execute()
        if not role_res.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User profile record not found."
            )
            
        role = role_res.data[0].get("role")
        if role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin role required."
            )
            
        return role_res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )

@router.post("/candidate")
async def candidate_chat(request: CandidateChatRequest):
    reply = await chat_with_candidate(message=request.message, session_id=request.session_id)
    return {"reply": reply}

@router.post("/hr")
async def hr_chat(request: HRChatRequest, admin: dict = Depends(verify_admin_token)):
    reply = await chat_with_hr(query=request.query)
    return {"reply": reply}
