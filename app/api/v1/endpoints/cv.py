import uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
import magic
from app.core.database import get_supabase_admin
from app.core.config import settings
from app.services.cv_parser import CVParser
from app.models.cv import CVUploadResponse
from app.services.ai.evaluator import evaluate_cv
from app.worker import evaluate_cv_task
from celery.result import AsyncResult
from pydantic import BaseModel
from typing import Any
from app.core.logging_config import request_id_var

router = APIRouter()

@router.post("/upload", response_model=CVUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_cv(
    file: UploadFile = File(...),
    candidate_id: Optional[str] = Form(None)
):
    # 1. Validate file format from filename extension
    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["pdf", "docx"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file format. Only PDF and DOCX files are allowed."
        )
    
    # Read file bytes synchronously inside FastAPI threadpool
    try:
        # Prevent reading more than 5MB to avoid memory exhaustion
        max_bytes = 5 * 1024 * 1024
        file_bytes = file.file.read(max_bytes + 1)
        if len(file_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds the 5MB limit."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}"
        )
    
    # Validate Magic Bytes and File Content (Macro / JS detection)
    try:
        CVParser.validate_file_content(file_bytes, filename)
        mime = magic.Magic(mime=True)
        detected_mime = mime.from_buffer(file_bytes)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to verify file bytes security: {str(e)}"
        )

    if ext == "pdf":
        if detected_mime != "application/pdf":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid file content. Expected PDF, but detected: {detected_mime}"
            )
    elif ext == "docx":
        # Word files can be identified as standard docx, zip, or octet-stream
        allowed_docx_mimes = [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            "application/octet-stream"
        ]
        if detected_mime not in allowed_docx_mimes:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid file content. Expected DOCX, but detected: {detected_mime}"
            )

    # 3. Parse text from CV synchronously
    parsed_text = ""
    if ext == "pdf":
        parsed_text = CVParser.parse_pdf(file_bytes)
    elif ext == "docx":
        parsed_text = CVParser.parse_docx(file_bytes)
        
    # 4. Connect to Supabase
    supabase = get_supabase_admin()
    
    # 5. Handle Candidate registration if candidate_id is not provided
    actual_candidate_id = None
    if candidate_id:
        # Verify candidate exists
        try:
            cand_res = supabase.table("candidates").select("id").eq("id", candidate_id).execute()
            if not cand_res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Candidate with ID {candidate_id} not found."
                )
            actual_candidate_id = cand_res.data[0]["id"]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database lookup failed: {str(e)}"
            )
    else:
        # Create a placeholder candidate
        try:
            clean_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
            cand_data = {
                "full_name": clean_name,
                "email": f"auto_{uuid.uuid4().hex[:8]}@example.com",
                "phone": None
            }
            cand_res = supabase.table("candidates").insert(cand_data).execute()
            if not cand_res.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to register candidate placeholder."
                )
            actual_candidate_id = cand_res.data[0]["id"]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to auto-create candidate record: {str(e)}"
            )

    # 6. Upload file to Supabase Storage
    unique_filename = f"{uuid.uuid4()}.{ext}"
    storage_path = f"cvs/{unique_filename}"
    
    try:
        # Uploading bytes to Supabase Storage
        storage_res = supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type or "application/octet-stream"}
        )
    except Exception as e:
        # Cleanup created candidate if upload fails and we auto-created it
        if not candidate_id and actual_candidate_id:
            try:
                supabase.table("candidates").delete().eq("id", actual_candidate_id).execute()
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_522_CONNECTION_TIMEOUT if "connection" in str(e).lower() else status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase storage upload failed: {str(e)}"
        )

    # 7. Insert CV Record into Database with status 'parsed'
    try:
        cv_record_data = {
            "candidate_id": actual_candidate_id,
            "file_path": storage_path,
            "file_name": filename,
            "file_size": len(file_bytes),
            "parsed_text": parsed_text,
            "status": "parsed"
        }
        db_res = supabase.table("cv_records").insert(cv_record_data).execute()
        if not db_res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save CV record to database."
            )
        record = db_res.data[0]
    except Exception as e:
        # Cleanup uploaded storage file and auto-created candidate on DB insert failure
        try:
            supabase.storage.from_(settings.SUPABASE_BUCKET).remove([storage_path])
            if not candidate_id and actual_candidate_id:
                supabase.table("candidates").delete().eq("id", actual_candidate_id).execute()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist CV record: {str(e)}"
        )

    return CVUploadResponse(
        id=record["id"],
        candidate_id=record["candidate_id"],
        file_name=record["file_name"],
        file_size=record["file_size"],
        status=record["status"],
        parsed_text_preview=parsed_text[:200] + "..." if len(parsed_text) > 200 else parsed_text,
        created_at=record["created_at"]
    )

class CVEvaluationTriggerResponse(BaseModel):
    task_id: str
    status: str

class CVTaskStatusResponse(BaseModel):
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None

@router.post("/{cv_id}/evaluate", response_model=CVEvaluationTriggerResponse)
async def evaluate_existing_cv(cv_id: uuid.UUID):
    supabase = get_supabase_admin()
    
    # 1. Fetch CV record from database to verify existence and check size/extension (Fail-fast)
    try:
        res = supabase.table("cv_records").select("id", "file_name", "file_size").eq("id", str(cv_id)).execute()
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CV record with ID {cv_id} not found."
            )
        record = res.data[0]
        file_name = record.get("file_name") or ""
        file_size = record.get("file_size") or 0
        
        # Check size (5MB limit)
        max_bytes = 5 * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fail-fast check failed: CV file size exceeds the 5MB limit."
            )
            
        # Check type
        ext = file_name.split(".")[-1].lower() if "." in file_name else ""
        if ext not in ["pdf", "docx"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fail-fast check failed: Unsupported file format. Only PDF and DOCX files are allowed."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query or validation failed: {str(e)}"
        )
        
    # 2. Trigger asynchronous Celery task with headers containing request_id
    try:
        request_id = request_id_var.get()
        task = evaluate_cv_task.apply_async(
            args=[str(cv_id)],
            headers={"request_id": request_id}
        )
        return CVEvaluationTriggerResponse(
            task_id=task.id,
            status="pending"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue CV evaluation task: {str(e)}"
        )

@router.get("/task-status/{task_id}", response_model=CVTaskStatusResponse)
def get_cv_task_status(task_id: str):
    res = AsyncResult(task_id)
    state = res.state.lower()
    
    if state == "success":
        return CVTaskStatusResponse(
            status="success",
            result=res.result
        )
    elif state == "failure":
        return CVTaskStatusResponse(
            status="failed",
            error=str(res.result)
        )
    elif state in ["pending", "started", "received", "retry"]:
        return CVTaskStatusResponse(
            status="pending"
        )
    else:
        return CVTaskStatusResponse(
            status="unknown"
        )
