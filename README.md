# AI-Powered CV Management & Grading System - Backend

Hệ thống quản lý, phân tích cú pháp và đánh giá CV tự động sử dụng trí tuệ nhân tạo (Google Gemini AI), tích hợp lưu trữ tệp tin thông qua Supabase Storage và cơ sở dữ liệu PostgreSQL.

---

## 🚀 Tech Stack

Hệ thống được xây dựng trên nền tảng các công nghệ hiện đại và bảo mật:
*   **Framework:** FastAPI (Python 3.11) - Hiệu năng cao, bất đồng bộ (async/await).
*   **AI Integration:** Google Gemini API (`gemini-3.5-flash`, `gemini-2.5-flash`) thông qua LangChain - Tự động chấm điểm, gợi ý vị trí công việc, phân tích điểm mạnh/điểm yếu với cấu trúc JSON chặt chẽ và cơ chế phòng chống Prompt Injection.
*   **Database & Storage:** Supabase (PostgreSQL & Supabase Storage) - Lưu trữ thông tin ứng viên, kết quả đánh giá và tệp tin CV gốc.
*   **Security & Hardening:** 
    *   Xác thực loại tệp tin bằng Magic Bytes (`python-magic` & `libmagic`).
    *   Giới hạn dung lượng tải lên tối đa 5MB.
    *   Cấu hình người dùng không có quyền root (`non-root user`) trong Docker để ngăn chặn leo thang đặc quyền.
    *   Bộ lọc Rate Limiting ghi dữ liệu ra tệp tin thread-safe (`/tmp/limiter_data.json`) bền vững khi khởi động lại container.
*   **DevOps:** Docker & Docker Compose - Đóng gói ứng dụng chạy độc lập, nhất quán môi trường.

---

## 🛠️ Hướng dẫn cài đặt & Khởi chạy

### 1. Cấu hình các biến môi trường
Tạo file `.env` tại thư mục gốc dự án (tham khảo file `.env.example`) và điền đầy đủ các thông tin:

```env
# Cấu hình kết nối Supabase
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-public-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_BUCKET=cv-records

# Cấu hình kết nối trực tiếp database PostgreSQL (cho HR SQL Agent)
DATABASE_URL=postgresql://postgres:password@db.your-project-id.supabase.co:5432/postgres

# Cấu hình AI / Google Gemini
GEMINI_API_KEY=your-gemini-api-key
```

### 2. Khởi chạy bằng Docker Compose
Khởi chạy hệ thống ở chế độ background (sau khi chỉnh sửa code hệ thống sẽ tự động build lại):

```bash
docker-compose up -d --build
```
Hệ thống sẽ chạy tại địa chỉ: `http://localhost:8000`. Bạn có thể truy cập `http://localhost:8000/docs` để kiểm tra tài liệu API (Swagger UI).

---

## 🔄 Quy trình xử lý dữ liệu (Data Flow)

Dự án áp dụng quy trình xử lý khép kín giúp tối ưu tài nguyên lưu trữ và đảm bảo tính toàn vẹn dữ liệu:

```mermaid
graph TD
    A[Ứng viên / HR upload CV] --> B{Kiểm tra file}
    B -- Hợp lệ <= 5MB & đúng Magic Bytes --> C[Trích xuất text bằng PyMuPDF/python-docx]
    B -- Không hợp lệ --> D[Trả về lỗi 400/413/415]
    C --> E[Đăng ký Candidate Placeholder]
    E --> F[Upload tệp CV lên Supabase Storage bucket cv-records]
    F --> G[Lưu bản ghi CV record vào database public.cv_records]
    G --> H[HR yêu cầu Đánh giá CV]
    H --> I[Gửi text sang Gemini AI kèm System Prompt bảo mật]
    I --> J[Gemini trả về JSON theo Pydantic Schema]
    J --> K[Cập nhật status = evaluated & lưu JSON vào cột evaluation_result]
```

1.  **Tải lên & Xác thực:** 
    *   Hệ thống tiếp nhận tệp CV dạng PDF hoặc DOCX.
    *   Giới hạn dung lượng tải lên tối đa là **5MB** và xác thực định dạng bằng byte đầu tiên (Magic Bytes) để tránh việc giả mạo phần mở rộng tệp.
2.  **Trích xuất & Lưu trữ:** 
    *   Mã nguồn sử dụng `PyMuPDF` (PDF) và `python-docx` (DOCX) để đọc nội dung text của CV.
    *   Tệp CV gốc được tải lên thư mục `/cvs` thuộc **Supabase Storage bucket `cv-records`**.
    *   Thông tin được lưu xuống bảng `public.cv_records` bao gồm đường dẫn lưu trữ (`file_path`), nội dung text đã trích xuất (`parsed_text`), trạng thái ban đầu là `parsed`.
3.  **Phân tích & Đánh giá bằng AI:**
    *   Khi HR kích hoạt API đánh giá (`/cv/{cv_id}/evaluate`), hệ thống lấy `parsed_text` truyền sang Gemini AI.
    *   Prompt hệ thống được thiết lập chặt chẽ để phòng chống kỹ thuật **Prompt Injection** (không cho phép làm sai lệch điểm hoặc thực thi các câu lệnh lạ viết trong CV).
    *   Kết quả phân tích (điểm số, điểm mạnh, điểm yếu, vị trí đề xuất) được Gemini trả về dưới dạng JSON chuẩn hóa, sau đó lưu trực tiếp vào cột `evaluation_result` (kiểu dữ liệu `JSONB`) của bảng `cv_records` và cập nhật cột `status` thành `evaluated`.
4.  **Dọn dẹp tự động (Cleanup):**
    *   Script định kỳ `scripts/cleanup_cvs.py` sẽ tự động quét và xóa sạch các tệp CV trên Supabase Storage cũng như các bản ghi tương ứng trong cơ sở dữ liệu đã tồn tại quá **48 giờ** để bảo vệ quyền riêng tư và tiết kiệm không gian lưu trữ.
