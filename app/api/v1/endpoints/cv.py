import uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from app.core.database import get_supabase_admin
from app.core.config import settings
from app.services.cv_parser import CVParser
from app.models.cv import CVUploadResponse

router = APIRouter()

@router.post("/upload", response_model=CVUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    file: UploadFile = File(...),
    candidate_id: Optional[str] = Form(None)
):
    # 1. Validate file format
    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ["pdf", "docx"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file format. Only PDF and DOCX files are allowed."
        )
    
    # Read file bytes
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}"
        )
        
    # 2. Parse text from CV first (fail early if corrupted)
    parsed_text = ""
    if ext == "pdf":
        parsed_text = CVParser.parse_pdf(file_bytes)
    elif ext == "docx":
        parsed_text = CVParser.parse_docx(file_bytes)

    # 3. Connect to Supabase
    supabase = get_supabase_admin()
    
    # 4. Handle Candidate registration if candidate_id is not provided
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

    # 5. Upload file to Supabase Storage
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
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Supabase storage upload failed: {str(e)}"
        )

    # 6. Insert CV Record into Database
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
