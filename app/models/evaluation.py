from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class CriteriaEvaluation(BaseModel):
    score: float = Field(..., description="Điểm số cho tiêu chí này (từ 0.0 đến 10.0, hoặc -1.0 nếu thiếu dữ liệu trực quan)")
    comment: Optional[str] = Field(None, description="Nhận xét chi tiết dựa trên bằng chứng trong CV bằng tiếng Việt (tối đa 2-3 câu)")
    suggestion: Optional[str] = Field(None, description="Gợi ý cụ thể để cải thiện tiêu chí này bằng tiếng Việt (tối đa 2-3 câu)")

class WeaknessDetail(BaseModel):
    issue: str = Field(..., description="Tên/Mô tả điểm cần cải thiện cụ thể")
    suggestion: str = Field(..., description="Đoạn văn bản gợi ý hành động hoặc mẫu viết lại trực tiếp")

class CVEvaluationResult(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0, description="The evaluation score out of 10")
    detected_industry: str = Field(..., description="The detected industry or job family of the candidate's CV")
    strengths: List[str] = Field(..., description="List of candidate's strengths")
    weaknesses: List[WeaknessDetail] = Field(..., description="List of candidate's weaknesses with action suggestions")
    recommended_roles: List[str] = Field(..., description="List of recommended roles for the candidate")
    detailed_scores: Dict[str, CriteriaEvaluation] = Field(
        default_factory=dict,
        description="Dictionary mapping each of the 15 criteria to its detailed score, comment, and suggestion"
    )



