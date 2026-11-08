# Trợ Lý Văn Phòng AI (Bản Khung Skeleton)

Dự án Trợ lý Văn phòng AI an toàn với cơ chế **Human-in-the-loop (Người dùng kiểm soát)**, phân loại rủi ro công cụ (`read`, `reversible`, `confirm`), có TTL 10 phút cho các hành động chờ duyệt, chống duyệt trùng (idempotency) và ghi nhật ký kiểm toán (`audit_log`).

> **Giai đoạn hiện tại (Skeleton)**: Sử dụng `FakeLLM` và các mock provider (chưa tích hợp Google thật và chưa tích hợp RAG thật) để kiểm thử toàn diện khung luồng phê duyệt.

---

## 📁 Cấu Trúc Dự Án

```
tro-ly-van-phong/
├── AGENTS.md                  # Quy tắc cốt lõi, luật an toàn và tiêu chuẩn phân quyền tool
├── PROGRESS.md                # Theo dõi tiến độ triển khai và lộ trình tính năng
├── README.md                  # Tài liệu hướng dẫn cài đặt và sử dụng
├── docker-compose.yml         # Chạy cả backend và frontend qua Docker
├── .env.example               # Mẫu biến môi trường
├── docs/
│   └── SKELETON_SPEC.md       # Đặc tả kỹ thuật chi tiết của bản dựng khung
├── backend/
│   ├── requirements.txt       # Danh sách thư viện Python
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint (/chat, /actions/..., /audit)
│   │   ├── db.py              # SQLite schema (pending_actions, audit_log)
│   │   ├── agent/
│   │   │   ├── loop.py        # Vòng lặp agent: nhận tin nhắn -> LLM -> gọi tool/phân quyền
│   │   │   └── llm.py         # Interface LLMClient + FakeLLM trả lời có kịch bản
│   │   ├── tools/
│   │   │   ├── registry.py    # Đăng ký tool kèm risk: read | reversible | confirm
│   │   │   ├── email.py       # search_email (read), send_email (confirm), create_draft
│   │   │   ├── calendar.py    # list_events (read), create_event (confirm)
│   │   │   └── sheets.py      # read_range (read), delete_rows (confirm dry-run)
│   │   ├── confirm/
│   │   │   └── service.py     # Tạo pending, preview, approve, reject, TTL 10p, chống duyệt trùng
│   │   └── rag/
│   │       └── retriever.py   # Interface Retriever + StubRetriever trả về []
│   └── tests/
│       ├── test_confirm.py    # Unit tests cho confirm service (TTL, idempotency, edited_args)
│       └── test_agent_scenarios.py # Integration tests cho 4 kịch bản mẫu
└── frontend/
    ├── package.json
    ├── Dockerfile
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── App.tsx
        ├── types.ts
        └── components/
            ├── Chat.tsx         # Màn hình chat trực quan + gợi ý mẫu
            ├── ConfirmCard.tsx  # Thẻ "Cần xác nhận" (preview + 3 nút Duyệt / Sửa / Hủy)
            └── Toast.tsx        # Toast thông báo nổi
```

---

## 🚀 Hướng Dẫn Chạy Dự Án

### Cách 1: Chạy bằng Docker Compose (Khuyên dùng)

Chỉ với 1 câu lệnh để khởi động toàn bộ Backend và Frontend:

```bash
docker compose up --build
```

- **Frontend**: `http://localhost:5173`
- **Backend API & Swagger Docs**: `http://localhost:8000/docs`

---

### Cách 2: Chạy trực tiếp trên máy (Local)

#### 1. Chạy Backend (FastAPI)
```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
Backend sẽ khởi chạy tại `http://127.0.0.1:8000`. Database SQLite sẽ tự động khởi tạo tại `backend/app/app.db`.

#### 2. Chạy Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Mở trình duyệt truy cập: `http://localhost:5173`.

---

## 🧪 Chạy Kiểm Thử (Unit Tests)

Backend đã được trang bị đầy đủ bộ test cho luồng xác nhận và các kịch bản hành vi:

```bash
# Chạy toàn bộ test
python -m pytest backend/tests -v
```

Bộ test bao gồm:
1. `test_tool_confirm_does_not_execute_before_approval`: Tool confirm không chạy khi chưa duyệt.
2. `test_double_approval_only_executes_once`: Duyệt 2 lần chỉ chạy 1 lần (Idempotency).
3. `test_expired_action_cannot_be_approved`: Quá thời hạn 10 phút thì không duyệt được (`ActionExpiredError`).
4. `test_approve_with_edited_args_replaces_original_and_audits_both`: Hỗ trợ tham số chỉnh sửa `edited_args` và lưu vết vào `audit_log`.
5. `test_scenario_1_search_email_runs_immediately`: Kịch bản 1 tìm email chạy ngay lập tức.
6. `test_scenario_2_and_3_send_email_and_approve_or_reject`: Kịch bản 2 & 3 gửi email, duyệt, hủy.
7. `test_scenario_4_delete_rows_shows_dry_run_preview`: Kịch bản 4 dry-run xóa dòng sheet.

---

## 🎯 4 Kịch Bản Hoạt Động Cần Kiểm Thử

| # | Câu lệnh người dùng | Mức độ rủi ro | Hành vi hệ thống |
|---|---|---|---|
| **1** | `tìm email của Minh` | `read` | Chạy tức thì, hiển thị danh sách email tìm thấy. |
| **2** | `gửi email cho Minh nội dung Báo cáo tuần đã xong` | `confirm` | **KHÔNG** gửi ngay; xuất hiện thẻ **Cần xác nhận** hiển thị To, Tiêu đề, Nội dung. |
| **3** | Bấm **Duyệt** hoặc **Hủy** trên thẻ | - | - Bấm **Duyệt**: Mock email được "gửi" và ghi vào `audit_log`.<br>- Bấm **Hủy**: Lệnh bị hủy bỏ, không gửi.<br>- Bấm **Sửa**: Hiện toast *"Chức năng đang phát triển"*. |
| **4** | `xóa 10 dòng đầu sheet Doanh thu` | `confirm` | Chạy **dry-run** tính toán số dòng, hiển thị bảng dữ liệu mẫu vài dòng sắp bị xóa và chờ xác nhận. |

---

## 📡 Danh Sách API Endpoints

- `POST /chat`: Gửi tin nhắn tới Agent và nhận phản hồi (hoặc pending action).
- `GET /actions/pending`: Lấy danh sách hành động đang chờ duyệt.
- `GET /actions/{id}`: Xem chi tiết một hành động chờ duyệt (tự động cập nhật `EXPIRED` nếu quá 10 phút).
- `POST /actions/{id}/approve`: Duyệt thực thi hành động (chống duyệt đúp, hỗ trợ `edited_args`).
- `POST /actions/{id}/reject`: Hủy bỏ hành động chờ duyệt.
- `GET /audit`: Xem danh sách nhật ký kiểm toán hệ thống.
- `GET /health`: Kiểm tra trạng thái máy chủ.
