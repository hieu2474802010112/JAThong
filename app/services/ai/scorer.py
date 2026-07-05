"""
scorer.py — CV Score Calculation Engine
-----------------------------------------
Contains all Python-side arithmetic scoring logic.
This module runs AFTER the Gemini AI returns a raw CVEvaluationResult and applies
additional business rules to produce the final calibrated score.

Public API:
  - clean_text(raw_text: str) -> str
  - get_dynamic_criteria() -> str
  - clear_criteria_cache()
  - calculate_final_score(result: CVEvaluationResult, raw_text: str) -> float
"""
import re
import redis
from cachetools import TTLCache
from app.models.evaluation import CVEvaluationResult, WeaknessDetail
from app.core.database import get_supabase_admin
from app.core.config import settings
from app.core.prompt_manager import get_system_prompt


# ──────────────────────────────────────────────
# Redis L2 cache (shared across worker processes)
# ──────────────────────────────────────────────
try:
    _redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
    _redis_client = redis.Redis(connection_pool=_redis_pool)
except Exception:
    _redis_client = None

# In-process L1 cache (TTL = 24 h, max 10 rubric versions)
_criteria_cache: TTLCache = TTLCache(maxsize=10, ttl=86400)


# ──────────────────────────────────────────────
# Text pre-processing
# ──────────────────────────────────────────────

def clean_text(raw_text: str) -> str:
    """
    Normalise raw extracted PDF text before passing to Gemini.
    - Collapses multiple spaces/tabs into one
    - Collapses 3+ consecutive blank lines into two newlines
    """
    if not raw_text:
        return ""
    cleaned = raw_text.strip()
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned


# ──────────────────────────────────────────────
# Dynamic Rubric (DB → Redis → In-process → Hardcoded fallback)
# ──────────────────────────────────────────────

def get_dynamic_criteria() -> str:
    """
    Return the active scoring rubric text using a 3-level cache strategy:
      L1  In-process TTLCache (instant, zero I/O)
      L2  Redis (shared across workers, survives process restart)
      L3  Supabase `evaluation_settings` table
      L4  Hardcoded fallback (always available)
    """
    cache_key = "default_cv_rubric"

    # L1 — in-process
    if cache_key in _criteria_cache:
        return _criteria_cache[cache_key]

    # L2 — Redis
    if _redis_client:
        try:
            cached = _redis_client.get(cache_key)
            if cached:
                _criteria_cache[cache_key] = cached
                return cached
        except Exception:
            pass

    # L3 — Supabase
    try:
        supabase = get_supabase_admin()
        res = (
            supabase.table("evaluation_settings")
            .select("criteria_text")
            .eq("setting_key", cache_key)
            .execute()
        )
        if res.data:
            criteria = res.data[0].get("criteria_text")
            if criteria:
                _criteria_cache[cache_key] = criteria
                if _redis_client:
                    try:
                        _redis_client.set(cache_key, criteria)
                    except Exception:
                        pass
                return criteria
    except Exception:
        pass

    # L4 — Hardcoded fallback rubric
    fallback = (
        "ANALYSIS GUIDELINES:\n"
        "1. Determine the Industry and Job Family of the candidate's CV (assign this to 'detected_industry').\n"
        "2. Evaluate the CV using the HYBRID SCORING SYSTEM on a 10-point scale. Follow these exact steps to compute the final 'score':\n"
        "   - STEP 1: Start with a base of 10.0 points.\n"
        "   - STEP 2: FORMAT DEDUCTIONS (Trừ điểm hình thức): Apply the following exact deductions (do not vary these numbers):\n"
        "     * Structure & Layout / Minor Spacing: Deduct only 0.2 - 0.3 points if the layout is cluttered, lacks information hierarchy, or missing clear Heading hierarchy. Do NOT deduct for plain black-and-white ATS-friendly layout.\n"
        "     * Career Objective / Profile Summary: Deduct 1.0 points if the career objective/profile summary is completely absent OR fails to clearly convey direction.\n"
        "       - CAREER OBJECTIVE MITIGATION RULE: If missing entirely, its component score is overridden to 9.5 (treating it as a minor 0.5-point deduction) and it is completely isolated/excluded from triggering any Weakness Caps or restricting the final score.\n"
        "       - MINOR DEDUCTION RULE: Grouped short-term/long-term goals or minor omissions in objective are only penalized 0.2 - 0.3 points on component scores.\n"
        "     * Work Experience dates: Deduct 1.0 points for EACH work experience entry that fails to provide specific start and end dates with BOTH month and year (e.g., 'OCT/2023 - FEB/2024' or '10/2023 - 02/2024' are acceptable). If it only says '2024', '2024 - Nay', or omits month entirely, apply this deduction per entry.\n"
        "     * Skills listing: Deduct 0.3 - 0.5 points if subjective skill ratings are used (e.g., rating skills 8/10, 80%, using progress bars, star ratings, or bar charts in the CV text). Listing skill names without ratings is correct and should NOT be penalised.\n"
        "       NOTE: This is a visual/decorative flaw — its penalty weight is much lower than missing actual experience data.\n"
        "     * Portfolio link / Social Spam check: Deduct 1.0 points if the CV is for an IT, Marketing, Creative, Art/Design, or Media industry role and lacks any link to a portfolio.\n"
        "       * FULL EXEMPTION (0 deduction): Kế toán / HR / Nhân sự / Sales / Kinh doanh / Admin / Logistics / Supply Chain — thiếu Portfolio là bình thường, KHÔNG trừ điểm.\n"
        "       * For other non-creative roles: Missing portfolio is a minor issue, deduct at most 0.2 - 0.3 points.\n"
        "       * SOCIAL SPAM RULE:\n"
        "         - Tech/Dev/Data/IT fields: Personal social media links (Facebook, Instagram, TikTok) without a professional portfolio (GitHub, GitLab, Kaggle, tech blog) = Social Spam → deduct 1.0 points.\n"
        "         - Sales / HR / Nhân sự / Tuyển dụng fields: Personal social media (Facebook, TikTok) IS ACCEPTED if it demonstrates personal branding, community building, or professional presence. Do NOT penalize.\n"
        "         - Other non-creative roles: treat personal social links as a minor issue only.\n"
        "     * Contact Information: Deduct 0.5 points if either Email or Phone number is completely missing. Deduct 0.5 points if the email address is unprofessional (contains informal/slang words such as 'cute', 'boy', 'girl', 'baby', 'sexy', etc.).\n"
        "   - INDUSTRY-SPECIFIC RUBRIC GUIDELINES:\n"
        "     * Trade Marketing / Commerce: Value quantitative channel management metrics (Modern Trade/MT, Wholesale), POSM compliance, GSO target fulfillment, and promotion budget/efficiency optimization.\n"
        "     * Digital Sales / Biz Dev / E-commerce: Value data-driven mindset (PowerBI, SQL), hands-on E-commerce store management, and proactive sponsorship/revenue negotiation.\n"
        "     * Human Resources (HR): Value specialist keywords (Talent Mapping, Performance Management, L&D) and quantitative HR metrics.\n"
        "   - STEP 3: QUALITY ADJUSTMENTS:\n"
        "     * Content Penalty: Deduct up to 1.0 points for shallow bullet points with no outcomes or metrics.\n"
        "     * Component Bonus Points: Add up to 1.0 points for outstanding achievements, awards or publications.\n"
        "   - STEP 4: FINAL SCORE CALCULATION & LOOSENED WEAKNESS CAPS:\n"
        "     * Compute: 10.0 - (Format Deductions) - (Content Penalty) + (Component Bonus).\n"
        "     * LOOSENED WEAKNESS CAPS (only applies to Content Quality issues — NOT to minor format issues):\n"
        "       - Only count weaknesses about: shallow bullet points, missing quantitative KPI, generic/hollow descriptions, misleading information.\n"
        "       - Do NOT count minor format issues towards caps: missing portfolio, skills rating bars, social spam, missing month/year in dates, layout/font, career objective (separately mitigated).\n"
        "       - 1-2 content quality weaknesses: Cap max 9.6.\n"
        "       - 3-4 content quality weaknesses: Cap max 8.8.\n"
        "       - >= 5 major content quality weaknesses: Cap max 7.0.\n"
        "     * FLAT DIRECT OVERALL BONUS: If candidate has published scientific papers OR achieved Champion/Runner-up at major competitions, add +0.7 to +1.0 directly to the final overall score (capped at 10.0).\n"
        "     * The final score MUST be mathematically precise and consistent with weaknesses.\n"
        "3. Output rules:\n"
        "   - strengths: Mảng chứa tối đa 3 gạch đầu dòng điểm mạnh của ứng viên (tiếng Việt súc tích, < 20 từ/dòng).\n"
        "   - weaknesses: Mảng chứa các Object đại diện cho các Điểm cần cải thiện. Mỗi Object bắt buộc gồm:\n"
        "     * issue: Tên/Mô tả điểm cần cải thiện cụ thể bằng tiếng Việt.\n"
        "     * suggestion: Đoạn văn bản gợi ý hành động hoặc mẫu viết lại trực tiếp.\n"
        "       - AI SUGGESTION GENERATION LOGIC:\n"
        "         + Nếu CV thiếu mục tiêu nghề nghiệp/summary: suggestion phải tự động tạo ra 2 mẫu câu mục tiêu tiếng Anh chuẩn chuyên nghiệp phù hợp với ngành.\n"
        "         + Nếu một dòng kinh nghiệm thiếu KPI định lượng: suggestion phải trích xuất chính dòng mô tả đó và viết lại một phiên bản giả định có kèm số liệu KPI thực tế.\n"
        "   - Recommended roles, strengths, weaknesses, and detected_industry must be written in Vietnamese.\n"
        "   - The keys and overall structure must strictly follow the Pydantic schema."
    )

    _criteria_cache[cache_key] = fallback
    if _redis_client:
        try:
            _redis_client.set(cache_key, fallback)
        except Exception:
            pass
    return fallback


def clear_criteria_cache() -> None:
    """Invalidate both L1 and L2 caches (call after admin updates rubric in DB)."""
    _criteria_cache.clear()
    if _redis_client:
        try:
            _redis_client.delete("default_cv_rubric")
        except Exception:
            pass


# ──────────────────────────────────────────────
# Industry detection helpers (used by calculate_final_score)
# ──────────────────────────────────────────────

_TECH_KEYWORDS = [
    "công nghệ", "kỹ thuật", "it", "developer", "software", "data",
    "system", "lập trình", "mạng", "computer", "dev", "tech", "analyst",
]
_CREATIVE_MKT_KEYWORDS = [
    "marketing", "creative", "design", "thiết kế", "art", "media",
    "truyền thông", "content", "sáng tạo", "mkt",
]
_PORTFOLIO_EXEMPT_KEYWORDS = [
    "kế toán", "accounting", "hr", "nhân sự", "human resource",
    "sales", "kinh doanh", "admin", "hành chính",
    "logistics", "vận tải", "chuỗi cung ứng", "supply chain",
]
_SOCIAL_BRANDING_OK_KEYWORDS = [
    "sales", "kinh doanh", "hr", "nhân sự", "human resource",
    "tuyển dụng", "recruitment",
]

# Keywords whose weaknesses are excluded from the Weakness Caps count
_MINOR_FORMAT_EXCLUSION_KEYWORDS = [
    # Objective (mitigated separately)
    "mục tiêu", "profile summary", "tóm tắt", "định hướng", "thiếu mục tiêu",
    # Portfolio / Links
    "portfolio", "link minh chứng", "link portfolio", "github", "gitlab",
    # Social spam
    "mạng xã hội", "social", "instagram", "facebook", "tiktok",
    # Rating bars
    "rating kỹ năng", "thanh kỹ năng", "tiêu chí kỹ năng", "đánh giá kỹ năng", "progress bar",
    # Layout / Typography
    "bố cục", "trình bày", "font", "màu sắc", "layout",
    # Missing month/year (already deducted directly)
    "mốc thời gian", "tháng/năm", "thiếu tháng", "thiếu ngày",
]


def _get_val(v) -> float:
    """Extract numeric score from a criteria value (dict, Pydantic object, or raw number)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "score" in v:
        return float(v["score"])
    return float(getattr(v, "score", -1.0))


# ──────────────────────────────────────────────
# Main scoring function
# ──────────────────────────────────────────────

def calculate_final_score(result: CVEvaluationResult, raw_text: str = "") -> float:
    """
    Apply Python business rules on top of the raw Gemini score.

    Steps:
      1. Industry detection (Tech / Creative-Mkt / Portfolio-exempt / Social-branding-ok)
      2. Social Spam check → penalise Portfolio score & add WeaknessDetail if needed
      3. Career Objective Mitigation → override missing objective score to 9.5
      4. Compute base score as average of valid detailed_scores with floor guards
      5. Loosened Weakness Caps (content quality only, not minor format issues)
      6. Remove objective-related weaknesses from display list
      7. Flat bonus for publications / competition achievements
      8. Dynamic floor (5.5 or 6.0 for strong experience+skills)
      9. Return rounded to 1 decimal, clamped [floor, 10.0]
    """
    detailed = result.detailed_scores
    weaknesses = result.weaknesses

    if not detailed:
        return round(result.score, 1)

    # ── 1. Industry flags ──────────────────────────────────────────────
    ind_lower = result.detected_industry.lower()
    is_tech              = any(k in ind_lower for k in _TECH_KEYWORDS)
    is_creative_mkt      = any(k in ind_lower for k in _CREATIVE_MKT_KEYWORDS)
    is_portfolio_exempt  = any(k in ind_lower for k in _PORTFOLIO_EXEMPT_KEYWORDS)
    # is_social_branding_ok is used implicitly: exempt from social spam check via is_portfolio_exempt

    # ── 2. Social Spam check ───────────────────────────────────────────
    if raw_text and not is_creative_mkt and not is_portfolio_exempt:
        raw_lower = raw_text.lower()
        _social_domains = ["instagram.com", "facebook.com", "fb.com", "tiktok.com", "threads.net"]
        has_social = (
            any(s in raw_lower for s in _social_domains)
            or any(k in raw_lower for k in ["instagram", "facebook", "tiktok", "threads"])
        )
        _pro_domains = ["github.com", "gitlab.com", "kaggle.com", "medium.com", "linkedin.com", "linktr.ee"]
        has_pro_portfolio = (
            any(t in raw_lower for t in _pro_domains)
            or any(k in raw_lower for k in ["github", "gitlab", "kaggle"])
        )

        if has_social and not has_pro_portfolio:
            spam_comment = "Cảnh báo: Link Portfolio là mạng xã hội cá nhân không liên quan đến ngành chuyên môn."
            for key in list(detailed.keys()):
                if "link minh chứng" in key.lower() or "portfolio" in key.lower():
                    if isinstance(detailed[key], dict):
                        detailed[key]["score"] = 8.0
                        detailed[key]["comment"] = spam_comment
                    else:
                        try:
                            setattr(detailed[key], "score", 8.0)
                            setattr(detailed[key], "comment", spam_comment)
                        except Exception:
                            pass

            warning = WeaknessDetail(
                issue="Cảnh báo: Link Portfolio là mạng xã hội cá nhân không liên quan đến ngành chuyên môn kỹ thuật/nghiệp vụ.",
                suggestion="Bạn nên sử dụng đường dẫn Github, Behance, hoặc Personal Portfolio chuyên nghiệp thay vì liên kết mạng xã hội cá nhân.",
            )
            if not result.weaknesses:
                result.weaknesses = [warning]
            else:
                existing_issues = {(w.issue if hasattr(w, "issue") else str(w)) for w in result.weaknesses}
                if warning.issue not in existing_issues:
                    result.weaknesses.append(warning)

    # ── 3. Career Objective Mitigation ────────────────────────────────
    has_missing_objective = False
    obj_score = 10.0

    if weaknesses:
        for w in weaknesses:
            w_text = w.issue if hasattr(w, "issue") else str(w)
            w_lower = w_text.lower()
            if "thiếu" in w_lower and (
                "mục tiêu" in w_lower or "profile summary" in w_lower or "tóm tắt" in w_lower
            ):
                has_missing_objective = True
                break

    for key, v in detailed.items():
        if "Mục tiêu nghề nghiệp" in key:
            obj_score = _get_val(v)
            break

    if obj_score < 5.0 or has_missing_objective:
        has_missing_objective = True
        obj_score = 9.5
        for key in list(detailed.keys()):
            kl = key.lower()
            if "mục tiêu" in kl or "tóm tắt" in kl or "profile summary" in kl:
                if isinstance(detailed[key], dict):
                    detailed[key]["score"] = 9.5
                elif isinstance(detailed[key], (int, float)):
                    detailed[key] = 9.5
                else:
                    try:
                        setattr(detailed[key], "score", 9.5)
                    except Exception:
                        pass

    # ── 4. Base score calculation ──────────────────────────────────────
    try:
        valid_scores = []
        for key, v in detailed.items():
            val = _get_val(v)
            if val < 0.0:
                continue

            kl = key.lower()

            # ATS Exemption: skip zero extracurricular scores for Tech candidates
            if is_tech and "hoạt động ngoại khóa" in kl and val <= 1.0:
                continue

            # Sub-objective floor: limit deduction vs main objective score
            if ("mục tiêu ngắn hạn" in kl or "mục tiêu dài hạn" in kl) and obj_score >= 7.0:
                val = max(val, obj_score - 0.3)

            # Layout/spelling floor: minor visual flaws capped at -2.0
            if any(k in kl for k in ["lỗi chính tả", "trình bày", "bố cục", "màu sắc", "font"]):
                val = max(val, 8.0)

            # Portfolio floor per industry
            if "link minh chứng" in kl or "portfolio" in kl:
                if is_portfolio_exempt:
                    val = max(val, 10.0)   # full exemption
                elif not is_creative_mkt:
                    val = max(val, 8.0)    # non-creative: minor deduction only

            # Skills rating floor: visual flaw, not a content flaw
            if any(k in kl for k in ["rating kỹ năng", "thanh kỹ năng", "đánh giá kỹ năng", "skill rating"]):
                val = max(val, 8.0)

            valid_scores.append(val)

        base_score = (sum(valid_scores) / len(valid_scores)) if valid_scores else result.score
    except Exception:
        base_score = result.score

    # ── 5. Loosened Weakness Caps (content quality only) ──────────────
    content_weaknesses = []
    if weaknesses:
        for w in weaknesses:
            w_text = w.issue if hasattr(w, "issue") else str(w)
            if not any(k in w_text.lower() for k in _MINOR_FORMAT_EXCLUSION_KEYWORDS):
                content_weaknesses.append(w)

    final_score = base_score
    n = len(content_weaknesses)
    if n >= 5 and final_score > 7.0:
        final_score = 7.0
    elif n >= 3 and final_score > 8.8:
        final_score = 8.8
    elif n >= 1 and final_score > 9.6:
        final_score = 9.6

    # ── 6. Remove objective-related weaknesses from display list ───────
    if has_missing_objective and result.weaknesses:
        _obj_keys = ["mục tiêu", "profile summary", "tóm tắt", "thiếu định hướng"]
        result.weaknesses = [
            w for w in result.weaknesses
            if not any(k in str(w).lower() for k in _obj_keys)
        ]

    # ── 7. Flat bonus for publications / competition wins ──────────────
    if raw_text:
        raw_lower = raw_text.lower()
        has_pub = any(
            k in raw_lower
            for k in ["publi", "paper", "research", "bài báo", "nghiên cứu", "olympiad", "kinh tế lượng"]
        )
        has_comp = any(
            k in raw_lower
            for k in ["champion", "runner", "winner", "prize", "quán quân", "á quân",
                       "giải", "contest", "leadership", "finalist", "semi-finalist", "doanh nhân tập sự"]
        )
        if has_pub and has_comp:
            final_score += 1.0
        elif has_pub or has_comp:
            final_score += 0.7

    # ── 8. Dynamic floor ──────────────────────────────────────────────
    floor_score = 5.5
    try:
        has_strong_exp = has_strong_skills = False
        for key, v in detailed.items():
            val = _get_val(v)
            kl = key.lower()
            if "kinh nghiệm" in kl and val >= 8.5:
                has_strong_exp = True
            if "kỹ năng cứng" in kl and val >= 8.5:
                has_strong_skills = True
        if has_strong_exp and has_strong_skills:
            floor_score = 6.0
    except Exception:
        pass

    return round(max(floor_score, min(10.0, final_score)), 1)
