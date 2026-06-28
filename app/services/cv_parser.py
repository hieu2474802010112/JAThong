import io
import fitz  # PyMuPDF
import docx  # python-docx
from fastapi import HTTPException, status

class CVParser:
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

