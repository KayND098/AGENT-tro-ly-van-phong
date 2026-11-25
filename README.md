# Trợ Lý Văn Phòng AI (Bản v1)

Hệ thống Trợ lý Văn phòng AI thông minh với nguyên tắc cốt lõi **Human-in-the-Loop**: các thao tác rủi ro cao (gửi email, xóa dữ liệu sheet) luôn bắt buộc tạo thẻ xác nhận, xem trước (preview/dry-run), hỗ trợ sửa tham số trước khi duyệt, tự hết hạn sau 10 phút, chống duyệt đúp và ghi vết kiểm toán đầy đủ.

---

## 1. Chạy Thử Nhanh (1 Lệnh duy nhất)

Chỉ cần cài đặt **Docker Desktop** trên máy tính:

1. **Chuẩn bị cấu hình**:
   ```bash
   cp .env.example .env
   ```
   *(Hoặc trên Windows PowerShell: `Copy-Item .env.example .env`)*.
   > **Mẹo**: Nếu không tạo `.env`, hệ thống vẫn tự động chạy ở chế độ **Demo** mặc định mà không cần khóa bí mật hay cấu hình tài khoản.

2. **Khởi động ứng dụng**:
   ```bash
   docker compose up --build
   ```

3. **Mở trình duyệt**:
   Truy cập: **[http://localhost:5173](http://localhost:5173)**
   Hệ thống tự động đăng nhập người dùng **Demo** với đầy đủ dữ liệu mẫu để thử nghiệm ngay lập tức.

---

## 2. Các Kịch Bản Thử Nghiệm Gợi Ý

Dưới đây là các câu lệnh bạn có thể thử ngay trên ô chat:

- **Tìm email nội bộ**:
  > Gõ: *"Tìm email về doanh thu quý 3"* hoặc *"Tìm email của Minh"*
  > *Hành vi*: Tool `search_email` (mức `read`) chạy ngay lập tức và trả về danh sách thư mẫu.

- **Gửi email (Thử luồng Duyệt / Sửa / Hủy)**:
  > Gõ: *"Gửi email cho Lan báo cáo doanh thu"*
  > *Hành vi*: Hệ thống **không** tự gửi email, mà tạo thẻ **Cần xác nhận** (preview dạng soạn thảo Gmail, đồng hồ đếm ngược 10 phút).
  > - Bấm **Duyệt**: Thực thi gửi email.
  > - Bấm **Sửa**: Mở hộp thoại cho phép chỉnh sửa người nhận, tiêu đề, nội dung rồi bấm *"Lưu và duyệt"*.
  > - Bấm **Hủy**: Hủy bỏ lệnh gửi.

- **Xóa dòng bảng tính (Dry-run preview)**:
  > Gõ: *"Xóa 3 dòng sheet Khách hàng"*
  > *Hành vi*: Tạo thẻ xác nhận hiển thị bản xem trước các dòng dữ liệu bị ảnh hưởng, kèm cảnh báo *"Không thể hoàn tác"*.

- **Tra cứu tài liệu nội bộ (RAG)**:
  > Gõ: *"Tìm tài liệu về quy định nghỉ phép"* hoặc *"Chính sách công tác phí thế nào?"*
  > *Hành vi*: Tool `search_documents` truy vấn SQLite FTS5 từ kho tài liệu mẫu (`data/docs`) và trích dẫn điều khoản chính xác.

- **Xem nhật ký kiểm toán (Audit Trail)**:
  > Chuyển sang tab **"Nhật ký"** trên thanh menu để xem toàn bộ lịch sử các thao tác đã thực thi, đã duyệt, đã sửa hoặc bị từ chối.

---

## 3. Sử Dụng Mô Hình Gemini Thật (Tùy Chọn)

Mặc định hệ thống dùng `LLM_PROVIDER=fake` (chạy ngoại tuyến, không tốn phí). Để sử dụng mô hình trí tuệ nhân tạo Gemini thật từ Google:

1. Mở file `.env` và thiết lập:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=AIzaSy...your_gemini_api_key...
   GEMINI_MODEL=gemini-3.8-flash
   ```
2. Khởi động lại: `docker compose up -d`

> ⚠️ **CẢNH BÁO BẢO MẬT**: Gói API miễn phí của Google có thể dùng dữ liệu trao đổi để cải thiện sản phẩm. Tuyệt đối **không** nhập thông tin cá nhân, mật khẩu hoặc dữ liệu cơ quan thực tế khi thử nghiệm với API key cá nhân.

---

## 4. Chế Độ Google Workspace Thật (`AUTH_MODE=google`)

Nếu muốn kết nối với tài khoản Google thật (OAuth 2.0 Web Application) thay vì tài khoản demo:

1. Truy cập **Google Cloud Console** > **APIs & Services** > **Credentials**.
2. Tạo mới **OAuth 2.0 Client ID** loại **Web Application**:
   - **Authorized redirect URIs**: Thêm `http://localhost:5173/auth/google/callback`
3. Tải file JSON bí mật về và lưu vào `backend/secrets/web_client_secret.json` (tuyệt đối không chia sẻ file này).
4. Trong file `.env`:
   ```env
   AUTH_MODE=google
   GOOGLE_WEB_CLIENT_FILE=backend/secrets/web_client_secret.json
   EMAIL_PROVIDER=google
   ```
5. Đăng nhập bằng tài khoản Google trên giao diện. Từng người dùng có thể kết nối Gmail riêng biệt qua menu tài khoản ở góc trên bên phải.

---

## 5. Quản Lý & Xử Lý Sự Cố Thường Gặp

### Các lệnh quản lý
- **Dừng hệ thống**:
  ```bash
  docker compose down
  ```
- **Xóa toàn bộ dữ liệu (reset database SQLite & volume)**:
  ```bash
  docker compose down -v
  ```

### Sự cố thường gặp
- **Cổng 5173 bị chiếm**: Kiểm tra xem máy bạn có ứng dụng khác đang chiếm cổng 5173 không (`netstat -ano | findstr :5173`). Đổi cổng ở phía host trong `docker-compose.yml` (ví dụ `"127.0.0.1:5174:80"`), nhưng lưu ý nếu dùng Google OAuth thì redirect URI phải khớp cổng.
- **Docker chưa chạy**: Đảm bảo ứng dụng Docker Desktop đã khởi động trước khi gõ lệnh compose.
- **Trang trắng hoặc không kết nối được backend**: Đảm bảo cả 2 container `office_assistant_frontend` và `office_assistant_backend` đều đang ở trạng thái `running` (`docker compose ps`).
- **Cảnh báo mạng LAN & An toàn**: Cổng chỉ được mở trên `127.0.0.1` (localhost). **Tuyệt đối KHÔNG đưa chế độ demo (`AUTH_MODE=demo`) lên môi trường mạng công khai hoặc Internet**, vì chế độ demo tự động cấp phiên truy cập cho bất kỳ ai truy cập.
