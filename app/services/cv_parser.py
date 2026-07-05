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
        cleaned_text = ""
        # 1. Try using pdfplumber for accurate layout-aware text extraction
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            # Normalize whitespaces, resolve double spacing, strip lines
            lines = []
            for line in text.split("\n"):
                cleaned_line = " ".join(line.strip().split())
                if cleaned_line:
                    lines.append(cleaned_line)
            temp_text = "\n".join(lines).strip()
            
            # Smart check: If pdfplumber squished words together (e.g. > 25 chars without space/special chars),
            # trigger fallback to PyMuPDF immediately.
            squished_count = 0
            for word in temp_text.split():
                if len(word) > 25:
                    if not any(c in word for c in ["@", "http", "www", "/", "."]):
                        squished_count += 1
            
            if squished_count < 3:
                cleaned_text = temp_text
        except Exception:
            # Fallback to PyMuPDF if pdfplumber fails
            cleaned_text = ""

        # 2. PyMuPDF (fitz) fallback path
        if not cleaned_text:
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                
                # Normalize whitespaces
                lines = []
                for line in text.split("\n"):
                    cleaned_line = " ".join(line.strip().split())
                    if cleaned_line:
                        lines.append(cleaned_line)
                cleaned_text = "\n".join(lines).strip()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Corrupted or invalid PDF file: {str(e)}"
                )


        if not cleaned_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="PDF file is empty or contains no readable text."
            )
        return cleaned_text


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
