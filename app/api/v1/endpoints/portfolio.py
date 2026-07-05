"""
Portfolio Builder — Simplified Conversational State Machine
=========================================================
FSM states (in order):
  question_1 → question_2 (optional) → done
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.database import get_supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── FSM configuration ────────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """
Bạn là Trợ lý Portfolio AI của JAThong. Hãy thực hiện kịch bản hội thoại 3 bước cố định bằng tiếng Việt:
- Bước 1 (Trạng thái question_1): Chào khách hàng và hỏi họ xem đã khám phá xong trang web hay chưa.
- Bước 2 (Trạng thái question_2): Nhắc nhở khách hàng thong thả xem và giới thiệu dịch vụ hỗ trợ của JAThong.
- Bước 3 (Trạng thái done): Cung cấp liên kết điền thông tin chi tiết: [👉 Điền thông tin Portfolio tại đây](/portfolio-form).

Tuân thủ nghiêm ngặt và không tự ý sáng tạo hay đi lệch kịch bản.
"""

STATES = [
    "question_1",
    "question_2",
    "done",
]

QUESTIONS: dict[str, str] = {
    "question_1": "Chào bạn! Không biết bạn đã khám phá xong trang web bên tôi hay chưa?",
    "question_2": "Bạn cứ thong thả khám phá nhé! Nếu bạn chưa biết cách làm một Portfolio như thế nào thì bên JAThong sẽ hỗ trợ hết mình.",
    "done": "Tuyệt vời! Bạn hãy bấm vào liên kết dưới đây để điền thông tin chi tiết. Bên JAThong sẽ liên hệ bạn sớm nhất nhé: [👉 Điền thông tin Portfolio tại đây](/portfolio-form)",
}

QUICK_REPLIES: dict[str, list[str]] = {
    "question_1": ["Có, tôi xem xong rồi", "Chưa, tôi đang xem"],
    "question_2": ["Yêu cầu hỗ trợ 🛠️"],
    "done": [],
}

# ─── Pydantic models ──────────────────────────────────────────────────────────

class MessageRequest(BaseModel):
    session_id: str
    message: str

class RollbackRequest(BaseModel):
    session_id: str

class MessageResponse(BaseModel):
    session_id: str
    reply: str
    quick_replies: list[str]
    progress_pct: int
    state: str
    data: dict
    edited_field: str | None = None

# ─── Redis Caching Setup for Session Performance under High Load ──────────────
import redis
import json
from app.core.config import settings

try:
    redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client = redis.Redis(connection_pool=redis_pool)
except Exception:
    redis_client = None

# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_session(session_id: str) -> dict:
    # 1. Read from Redis Cache first
    if redis_client:
        try:
            cached = redis_client.get(f"portfolio_session:{session_id}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # 2. Fallback to Supabase Database
    supabase = get_supabase_admin()
    res = supabase.table("portfolio_sessions") \
        .select("*") \
        .eq("id", session_id) \
        .limit(1) \
        .execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Portfolio session not found.")
    
    session = res.data[0]
    
    # Write back to Redis cache
    if redis_client:
        try:
            redis_client.setex(f"portfolio_session:{session_id}", 7200, json.dumps(session))  # 2 hours TTL
        except Exception:
            pass
            
    return session

def _autosave(session_id: str, state: str, data: dict, completed: bool = False):
    """Persist current FSM state + data immediately (autosave)."""
    supabase = get_supabase_admin()
    
    # 1. Update database
    supabase.table("portfolio_sessions").update({
        "state":         state,
        "data":          data,
        "completed":     completed,
    }).eq("id", session_id).execute()

    # 2. Update Redis Cache immediately
    if redis_client:
        try:
            session = {
                "id": session_id,
                "state": state,
                "data": data,
                "completed": completed
            }
            redis_client.setex(f"portfolio_session:{session_id}", 7200, json.dumps(session))  # 2 hours TTL
        except Exception:
            pass

def _create_support_request(session_id: str):
    """
    Insert a record into support_requests table.
    Enforces uniqueness constraint to avoid duplicate requests per session.
    """
    supabase = get_supabase_admin()
    try:
        # Check if a support request already exists for this session
        existing = supabase.table("support_requests") \
            .select("id") \
            .eq("session_id", session_id) \
            .execute()
        if not existing.data:
            supabase.table("support_requests").insert({
                "session_id": session_id,
                "status":     "PENDING"
            }).execute()
            logger.info(f"Created PENDING support request for session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to create support request (session_id: {session_id}): {e}")

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/session")
async def create_session():
    """Create a fresh chatbot session initialized."""
    supabase = get_supabase_admin()
    try:
        res = supabase.table("portfolio_sessions").insert({
            "state":         "question_1",
            "data":          {},
            "completed":     False,
        }).execute()
        session = res.data[0]
        return {
            "session_id":    session["id"],
            "reply":         QUESTIONS["question_1"],
            "quick_replies": QUICK_REPLIES["question_1"],
            "progress_pct":  0,
            "state":         "question_1",
            "data":          {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {e}")


@router.get("/session/{session_id}")
async def resume_session(session_id: str):
    """Resume an existing session."""
    session = _get_session(session_id)
    state   = session["state"]
    data    = session["data"] or {}

    # If the session has a legacy FSM state (from the old portfolio builder),
    # reset it to question_1 so the new flow runs correctly.
    valid_states = set(STATES)
    if state not in valid_states:
        state = "question_1"
        data  = {}
        _autosave(session["id"], state, data, completed=False)

    reply = QUESTIONS.get(state, QUESTIONS["question_1"])

    return {
        "session_id":    session_id,
        "reply":         reply,
        "quick_replies": QUICK_REPLIES.get(state, QUICK_REPLIES["question_1"]),
        "progress_pct":  100 if state == "done" else (50 if state == "question_2" else 0),
        "state":         state,
        "data":          data,
        "completed":     session["completed"] if state != "question_1" else False,
    }


@router.post("/message", response_model=MessageResponse)
async def send_message(req: MessageRequest):
    """
    Process user input and transition chatbot states.
    Triggers support requests when finishing the session.
    """
    session  = _get_session(req.session_id)
    state    = session["state"]
    data     = session["data"] or {}
    message  = req.message.strip()

    # Restart session if requested (via frontend reset mechanism or quick reply)
    if message == "🔄 Tạo Portfolio mới":
        return MessageResponse(
            session_id=req.session_id,
            reply=QUESTIONS["done"],
            quick_replies=QUICK_REPLIES["done"],
            progress_pct=100,
            state="done",
            data=data,
        )

    if state == "done":
        return MessageResponse(
            session_id=req.session_id,
            reply=QUESTIONS["done"],
            quick_replies=QUICK_REPLIES["done"],
            progress_pct=100,
            state="done",
            data=data,
        )

    if state == "question_1":
        msg_lower = message.lower()
        if "có" in msg_lower or "xong rồi" in msg_lower or "yes" in msg_lower:
            new_state = "done"
            data["q1_answer"] = message
            # Provide sentinel full_name so DB trigger (sync_portfolio_to_candidates) doesn't fail
            data.setdefault("full_name", "Portfolio Visitor")
            data.setdefault("email", f"portfolio_{req.session_id[:8]}@jathong.ai")
            try:
                _autosave(req.session_id, new_state, data, completed=True)
                _create_support_request(req.session_id)
            except Exception as e:
                logger.warning(f"Autosave on completion failed: {e}")
        else:
            new_state = "question_2"
            data["q1_answer"] = message
            _autosave(req.session_id, new_state, data, completed=False)
            
    elif state == "question_2":
        new_state = "done"
        data["q2_answer"] = message
        # Provide sentinel full_name so DB trigger (sync_portfolio_to_candidates) doesn't fail
        data.setdefault("full_name", "Portfolio Visitor")
        data.setdefault("email", f"portfolio_{req.session_id[:8]}@jathong.ai")
        try:
            _autosave(req.session_id, new_state, data, completed=True)
            _create_support_request(req.session_id)
        except Exception as e:
            logger.warning(f"Autosave on completion failed: {e}")
        
    else:
        new_state = "done"
        try:
            _autosave(req.session_id, new_state, data, completed=True)
        except Exception as e:
            logger.warning(f"Autosave failed: {e}")

    progress_pct = 100 if new_state == "done" else 50

    return MessageResponse(
        session_id=req.session_id,
        reply=QUESTIONS[new_state],
        quick_replies=QUICK_REPLIES.get(new_state, []),
        progress_pct=progress_pct,
        state=new_state,
        data=data,
    )


@router.post("/rollback")
async def rollback_session(req: RollbackRequest):
    session = _get_session(req.session_id)
    state   = session["state"]
    data    = session["data"] or {}

    if state == "question_1":
        return {
            "session_id":    req.session_id,
            "reply":         "⚠️ Không thể quay lại thêm nữa. Đây đã là bước đầu tiên.",
            "quick_replies": QUICK_REPLIES.get(state, []),
            "progress_pct":  0,
            "state":         state,
            "data":          data,
        }

    # Always rollback to question_1
    prev = "question_1"
    data = {}

    _autosave(req.session_id, prev, data, completed=False)

    reply = f"⬅️ Đã quay lại bước trước.\n\n{QUESTIONS[prev]}"
    return {
        "session_id":    req.session_id,
        "reply":         reply,
        "quick_replies": QUICK_REPLIES.get(prev, []),
        "progress_pct":  0,
        "state":         prev,
        "data":          data,
    }



