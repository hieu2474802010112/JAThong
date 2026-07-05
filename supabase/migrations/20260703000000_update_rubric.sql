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
2. Evaluate the CV on a 10-point scale according to HYBRID SCORING GUIDE:
   - Penalty (Trừ điểm hình thức):
     * Bố cục lộn xộn, thiếu phân cấp Heading: Trừ 0.5
     * Thiếu mục tiêu ngắn hạn và dài hạn rõ ràng: Trừ 1.0
     * Thiếu tháng/năm ở mục kinh nghiệm: Trừ 1.0/lỗi
     * Tự đánh giá kỹ năng bằng biểu đồ/phần trăm: Trừ 1.0
     * Các ngành liên quan đến IT, Marketing, Production, Creative, Sáng tạo Nghệ thuật/Thiết kế nhưng thiếu link Portfolio: Trừ 1.0 (các ngành khác không trừ điểm)
     * Thiếu Email/SĐT hoặc dùng Email thiếu chuyên nghiệp: Trừ 0.5
   - Quality (Chất lượng nội dung):
     * Phạt (-1.0): Nội dung sáo rỗng, đối phó.
     * Thưởng (+1.0): Có số liệu chứng minh hoặc chuyên môn xuất sắc.
3. OUTPUT COMPRESSION (Tối ưu hóa đầu ra JSON):
   - Mọi tiêu chí đạt >= 9.0 điểm (Xuất sắc): comment bắt buộc ghi nhận xét ngắn gọn khen ngợi thế mạnh vượt trội bằng tiếng Việt (dưới 20 từ), suggestion bắt buộc là null.
   - Mọi tiêu chí đạt 7.0 - 8.5 điểm (Trình độ tốt/Khá): comment và suggestion bắt buộc đặt là null.
   - Mọi tiêu chí < 7.0 điểm hoặc = -1.0 (Cần cải thiện/Thiếu dữ liệu): comment và suggestion bắt buộc ghi nhận xét và gợi ý súc tích tối đa bằng tiếng Việt (dưới 20 từ).
4. Output language:
   - The ''strengths'', ''weaknesses'', ''recommended_roles'', and ''detected_industry'' fields must be written in Vietnamese.
   - The keys and overall structure must strictly follow the Pydantic schema.',
    timezone('utc'::text, now())
)
ON CONFLICT (setting_key) DO UPDATE
SET criteria_text = EXCLUDED.criteria_text,
    updated_at = EXCLUDED.updated_at;
