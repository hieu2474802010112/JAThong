# Hướng dẫn Sử dụng Trang Quản trị Celery Flower (Giao diện Việt hóa)

Tài liệu này giải thích chi tiết các chức năng và cách sử dụng trang quản trị bất đồng bộ **Celery Flower** trong hệ thống chấm điểm và quản lý CV (JAThong).

---

## 1. Giới thiệu chung về Flower
**Flower** là một công cụ quản trị và giám sát thời gian thực (real-time) dành cho cụm tác vụ ngầm **Celery**. Hệ thống sử dụng Redis làm kênh truyền tin trung gian (Broker) và lưu trữ trạng thái. Giao diện Flower đã được Việt hóa và thiết lập giao diện tối (Premium Dark Mode) để tăng tính chuyên nghiệp và dễ quản trị.

Địa chỉ truy cập mặc định: **[http://localhost:5555](http://localhost:5555)**

---

## 2. Các chức năng chính trên Menu chính (Navbar)

### 2.1. Tiến trình (Workers)
Trang chủ hiển thị danh sách tất cả các worker đang kết nối và sẵn sàng xử lý tác vụ ngầm.
*   **Worker:** Tên định danh của worker container (ví dụ: `celery@cv-evaluator-worker`).
*   **Trạng thái (Status):** Cho biết worker đang trực tuyến (`Online`) hay ngoại tuyến (`Offline`).
*   **Đang chạy (Active):** Số lượng tác vụ hiện đang được worker thực thi tại thời điểm đó.
*   **Đã nhận (Processed):** Tổng số lượng tác vụ worker đã nhận kể từ khi khởi động.
*   **Thành công (Succeeded) / Thất bại (Failed):** Số lượng tác vụ hoàn thành tốt hoặc gặp lỗi ngoại lệ.
*   **Đã thử lại (Retried):** Số lượng tác vụ đã được tự động kích hoạt lại (nhờ cơ chế *Simple Retry* 3 lần mà hệ thống đã thiết lập).
*   **Tải trung bình (Load Average):** Chỉ số tải CPU của tiến trình xử lý trên worker.

### 2.2. Danh sách Tác vụ (Tasks)
Trang theo dõi lịch sử và chi tiết từng tác vụ chấm điểm CV (`evaluate_cv_task`).
*   **Tên Tác vụ (Name):** Tên hàm xử lý (mặc định là `app.worker.evaluate_cv_task`).
*   **Mã UUID:** Mã định danh duy nhất của tác vụ (ví dụ: `40f2de4d-3f89-4fc3-b1ca-1b5de489eeca`).
*   **Trạng thái (State):** Các trạng thái phổ biến bao gồm `PENDING` (chờ xử lý), `STARTED` (đang chạy), `SUCCESS` (hoàn thành), `FAILURE` (lỗi), hoặc `RETRY` (đang thử lại).
*   **Tham số (args / kwargs):** Dữ liệu truyền vào tác vụ. Đối với hệ thống này, `args` chính là `cv_id` dưới dạng UUID để truy vấn cơ sở dữ liệu.
*   **Kết quả / Lỗi (Result):** 
    *   Nếu thành công: Hiển thị chuỗi JSON kết quả chấm điểm (điểm số, điểm mạnh, điểm yếu).
    *   Nếu thất bại: Hiển thị thông điệp lỗi ngoại lệ chi tiết.
*   **Thời gian chạy (Runtime):** Tổng số giây tác vụ thực thi từ lúc bắt đầu đến khi kết thúc.
*   **Mã định tuyến (Routing Key) / Exchange:** Thông tin cấu hình luồng gửi nhận tin nhắn qua Redis.

### 2.3. Kênh truyền tin (Broker)
Trang giám sát cơ sở dữ liệu hàng đợi Redis.
*   **Hàng đợi (Queue):** Tên hàng đợi mặc định là `celery`.
*   **Số lượng Tin nhắn (Messages):** Tổng số tác vụ đang nằm trong hàng đợi chờ xử lý hoặc đang xử lý.
*   **Chưa xác nhận (Unacked):** Các tác vụ đang được worker xử lý nhưng chưa gửi xác nhận hoàn thành về Redis (bảo vệ bằng cờ `task_acks_late=True`).
*   **Sẵn sàng (Ready):** Các tác vụ mới được đẩy vào hàng đợi và đang đợi worker rảnh để xử lý.
*   **Người tiêu dùng (Consumers):** Số lượng luồng worker đang lắng nghe hàng đợi này.

---

## 3. Các chức năng cấu hình chi tiết (Khi Click vào từng Worker)

Khi bạn click vào một tiến trình cụ thể (ví dụ: `celery@cv-evaluator-worker`), Flower cung cấp các bảng điều khiển chuyên sâu:

### 3.1. Nhóm xử lý (Pool)
*   **Worker pool options:** Hiển thị số lượng tiến trình con chạy song song tối đa (`Max Concurrency` - mặc định là 16 tiến trình con) và thông tin chi tiết về prefetch count.
*   **Điều khiển kích thước Pool (Pool size control):**
    *   **Tăng (Grow) / Giảm (Shrink):** Cho phép bạn tăng hoặc giảm nóng số lượng luồng xử lý đồng thời của worker ngay lập tức mà không cần khởi động lại container.
    *   **Tự động co giãn (Auto scale):** Cấu hình dải giới hạn tối thiểu và tối đa để worker tự động điều chỉnh số lượng tiến trình con dựa trên khối lượng công việc thực tế.

### 3.2. Giới hạn (Limits)
Cho phép quản trị viên giới hạn tần suất xử lý để bảo vệ tài nguyên hệ thống hoặc tài khoản API AI bên thứ ba:
*   **Giới hạn Tần suất (Rate limit):** Điền số lượng tác vụ được phép chạy trong một khoảng thời gian (ví dụ: `10/m` nghĩa là tối đa 10 tác vụ trong 1 phút). Rất hữu ích khi cần khống chế lượt gọi đến Google Gemini API để tránh bị lỗi quá tải (HTTP 429).
*   **Thời gian chờ (Timeouts):** Thiết lập giới hạn thời gian chạy tối đa cho tác vụ trước khi tự động chấm dứt (Soft/Hard timeout).

### 3.3. Cấu hình (Config)
Liệt kê toàn bộ các thiết lập cấu hình của Celery đang hoạt động. Bạn có thể kiểm tra các tham số quan trọng như:
*   `task_serializer`: Định dạng tuần tự hóa dữ liệu (`json`).
*   `result_expires`: Thời gian hết hạn của kết quả trong bộ nhớ đệm (hệ thống đã cấu hình tối ưu là `1800` giây để tránh phình dung lượng RAM của Redis).

### 3.4. Hệ thống (System)
Hiển thị thống kê sử dụng tài nguyên hệ điều hành của container worker (`rusage`):
*   `utime` / `stime`: Thời gian CPU xử lý ở chế độ người dùng (user mode) và hệ thống (kernel mode).
*   `maxrss`: Lượng bộ nhớ RAM lớn nhất mà worker container đã chiếm dụng (đã được giới hạn cứng `mem_limit: 1g` trong docker-compose).
*   `nvcsw` / `nivcsw`: Số lần chuyển đổi ngữ cảnh tiến trình.
