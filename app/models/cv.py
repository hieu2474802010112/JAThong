from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class CVUploadResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    file_name: str
    file_size: int
    status: str
    parsed_text_preview: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
