from pydantic import BaseModel, Field
from typing import List

class CVEvaluationResult(BaseModel):
    score: int = Field(..., ge=0, le=100, description="The evaluation score out of 100")
    strengths: List[str] = Field(..., description="List of candidate's strengths")
    weaknesses: List[str] = Field(..., description="List of candidate's weaknesses")
    recommended_roles: List[str] = Field(..., description="List of recommended roles for the candidate")
