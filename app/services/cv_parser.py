import io
import zipfile
import fitz  # PyMuPDF
import docx  # python-docx
import magic
from fastapi import HTTPException, status

class CVParser:
    @staticmethod
    def validate_file_content(file_bytes: bytes, filename: str) -> None:
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty."
            )
            
        # Use python-magic to verify the actual file MIME type from magic bytes signature
        try:
            mime = magic.Magic(mime=True)
            detected_mime = mime.from_buffer(file_bytes)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security validation failed: Unable to parse file signature. Details: {str(e)}"
            )
            
        if ext == "docx":
            # Word files can be identified as openxml formats, zip, or octet-stream
            allowed_docx_mimes = [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/zip",
                "application/octet-stream"
            ]
            if detected_mime not in allowed_docx_mimes:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Security validation failed: File content does not match DOCX signature. Detected: {detected_mime}"
                )
                
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    file_list = zf.namelist()
                    # Check file name indicators for macros or executables
                    for name in file_list:
                        name_lower = name.lower()
                        if "vbaproject" in name_lower or name_lower.endswith(".bin"):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Security validation failed: Suspicious macro storage found (vbaProject.bin)."
                            )
                        if any(name_lower.endswith(e) for e in [".exe", ".dll", ".bat", ".cmd", ".vbs", ".js", ".scr"]):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Security validation failed: Suspicious executable content in document archive: {name}."
                            )
                            
                    # Scan Content Types XML for macro definitions
                    if "[Content_Types].xml" in file_list:
                        content_types = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore").lower()
                        if "vbaproject" in content_types or "macroenabled" in content_types:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Security validation failed: Suspicious macro content definition found in DOCX metadata."
                            )
            except zipfile.BadZipFile:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Corrupted or invalid Word document file."
                )
                
        elif ext == "pdf":
            if detected_mime != "application/pdf":
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Security validation failed: File content does not match PDF signature. Detected: {detected_mime}"
                )
            # Scan raw bytes for Javascript or Action execution triggers
            pdf_lower = file_bytes.lower()
            suspicious_tags = [b"/javascript", b"/js", b"/launch", b"/exec"]
            for tag in suspicious_tags:
                if tag in pdf_lower:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Security validation failed: Suspicious PDF content tag detected: '{tag.decode()}'."
                    )

    @staticmethod
    def parse_pdf(file_bytes: bytes) -> str:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            
            cleaned_text = text.strip()
            if not cleaned_text:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="PDF file is empty or contains no readable text."
                )
            return cleaned_text
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Corrupted or invalid PDF file: {str(e)}"
            )

    @staticmethod
    def parse_docx(file_bytes: bytes) -> str:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            text = [paragraph.text for paragraph in doc.paragraphs]
            cleaned_text = "\n".join(text).strip()
            if not cleaned_text:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="DOCX file is empty or contains no readable text."
                )
            return cleaned_text
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Corrupted or invalid DOCX file: {str(e)}"
            )
