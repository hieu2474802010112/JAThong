-- Ensure the table exists
CREATE TABLE IF NOT EXISTS public.evaluation_settings (
    id SERIAL PRIMARY KEY,
    setting_key TEXT UNIQUE NOT NULL,
    criteria_text TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Update or insert the default rubric criteria
INSERT INTO public.evaluation_settings (setting_key, criteria_text, updated_at)
VALUES (
    'default_cv_rubric',
    'ANALYSIS GUIDELINES:
1. Determine the Industry and Job Family of the candidate''s CV (assign this to ''detected_industry'').
2. Evaluate the CV using the HYBRID SCORING SYSTEM on a 10-point scale. Follow these exact steps to compute the final ''score'':
   - STEP 1: Start with a base of 10.0 points.
   - STEP 2: FORMAT DEDUCTIONS (Trừ điểm hình thức): Apply the following exact deductions (do not vary these numbers):
     * Structure & Layout / Minor Spacing: Deduct only 0.2 - 0.3 points if the layout is cluttered, lacks information hierarchy, or missing clear Heading hierarchy. Do NOT deduct for plain black-and-white ATS-friendly layout.
     * Career Objective / Profile Summary: Deduct 1.0 points if the career objective/profile summary is completely absent OR fails to clearly convey direction.
       - CAREER OBJECTIVE MITIGATION RULE: If missing entirely, its component score is overridden to 9.5 (treating it as a minor 0.5-point deduction) and it is completely isolated/excluded from triggering any Weakness Caps or restricting the final score.
       - MINOR DEDUCTION RULE: Grouped short-term/long-term goals or minor omissions in objective are only penalized 0.2 - 0.3 points on component scores.
     * Work Experience dates: Deduct 1.0 points for EACH work experience entry that fails to provide specific start and end dates with BOTH month and year (e.g., ''OCT/2023 - FEB/2024'' or ''10/2023 - 02/2024'' are acceptable). If it only says ''2024'', ''2024 - Nay'', or omits month entirely, apply this deduction per entry.
     * Skills listing: Deduct 0.3 - 0.5 points if subjective skill ratings are used (e.g., rating skills 8/10, 80%, using progress bars, star ratings, or bar charts in the CV text). Listing skill names without ratings is correct and should NOT be penalised.
       NOTE: This is a visual/decorative flaw — its penalty weight is much lower than missing actual experience data.
     * Portfolio link / Social Spam check: Deduct 1.0 points if the CV is for an IT, Marketing, Creative, Art/Design, or Media industry role and lacks any link to a portfolio.
       * FULL EXEMPTION (0 deduction): Kế toán / HR / Nhân sự / Sales / Kinh doanh / Admin / Logistics / Supply Chain — thiếu Portfolio là bình thường, KHÔNG trừ điểm.
       * For other non-creative roles: Missing portfolio is a minor issue, deduct at most 0.2 - 0.3 points.
       * SOCIAL SPAM RULE:
         - Tech/Dev/Data/IT fields: Personal social media links (Facebook, Instagram, TikTok) without a professional portfolio (GitHub, GitLab, Kaggle, tech blog) = Social Spam → deduct 1.0 points.
         - Sales / HR / Nhân sự / Tuyển dụng fields: Personal social media (Facebook, TikTok) IS ACCEPTED if it demonstrates personal branding, community building, or professional presence. Do NOT penalize.
         - Other non-creative roles: treat personal social links as a minor issue only.
     * Contact Information: Deduct 0.5 points if either Email or Phone number is completely missing. Deduct 0.5 points if the email address is unprofessional (contains informal/slang words such as ''cute'', ''boy'', ''girl'', ''baby'', ''sexy'', etc.).
   - INDUSTRY-SPECIFIC RUBRIC GUIDELINES:
     * Trade Marketing / Commerce: Value quantitative channel management metrics (Modern Trade/MT, Wholesale), POSM compliance, GSO target fulfillment, and promotion budget/efficiency optimization.
     * Digital Sales / Biz Dev / E-commerce: Value data-driven mindset (PowerBI, SQL), hands-on E-commerce store management, and proactive sponsorship/revenue negotiation.
     * Human Resources (HR): Value specialist keywords (Talent Mapping, Performance Management, L&D) and quantitative HR metrics.
   - STEP 3: QUALITY ADJUSTMENTS:
     * Content Penalty: Deduct up to 1.0 points for shallow bullet points with no outcomes or metrics.
     * Component Bonus Points: Add up to 1.0 points for outstanding achievements, awards or publications.
   - STEP 4: FINAL SCORE CALCULATION & LOOSENED WEAKNESS CAPS:
     * Compute: 10.0 - (Format Deductions) - (Content Penalty) + (Component Bonus).
     * LOOSENED WEAKNESS CAPS (only applies to Content Quality issues — NOT to minor format issues):
       - Only count weaknesses about: shallow bullet points, missing quantitative KPI, generic/hollow descriptions, misleading information.
       - Do NOT count minor format issues towards caps: missing portfolio, skills rating bars, social spam, missing month/year in dates, layout/font, career objective (separately mitigated).
       - 1-2 content quality weaknesses: Cap max 9.6.
       - 3-4 content quality weaknesses: Cap max 8.8.
       - >= 5 major content quality weaknesses: Cap max 7.0.
     * FLAT DIRECT OVERALL BONUS: If candidate has published scientific papers OR achieved Champion/Runner-up at major competitions, add +0.7 to +1.0 directly to the final overall score (capped at 10.0).
     * The final score MUST be mathematically precise and consistent with weaknesses.
3. Output rules:
   - strengths: Mảng chứa tối đa 3 gạch đầu dòng điểm mạnh của ứng viên (tiếng Việt súc tích, < 20 từ/dòng).
   - weaknesses: Mảng chứa các Object đại diện cho các Điểm cần cải thiện. Mỗi Object bắt buộc gồm:
     * issue: Tên/Mô tả điểm cần cải thiện cụ thể bằng tiếng Việt.
     * suggestion: Đoạn văn bản gợi ý hành động hoặc mẫu viết lại trực tiếp.
       - AI SUGGESTION GENERATION LOGIC:
         + Nếu CV thiếu mục tiêu nghề nghiệp/summary: suggestion phải tự động tạo ra 2 mẫu câu mục tiêu tiếng Anh chuẩn chuyên nghiệp phù hợp với ngành.
         + Nếu một dòng kinh nghiệm thiếu KPI định lượng: suggestion phải trích xuất chính dòng mô tả đó và viết lại một phiên bản giả định có kèm số liệu KPI thực tế.
   - Recommended roles, strengths, weaknesses, and detected_industry must be written in Vietnamese.
   - The keys and overall structure must strictly follow the Pydantic schema.',
    timezone('utc'::text, now())
)
ON CONFLICT (setting_key) DO UPDATE
SET criteria_text = EXCLUDED.criteria_text,
    updated_at = EXCLUDED.updated_at;
