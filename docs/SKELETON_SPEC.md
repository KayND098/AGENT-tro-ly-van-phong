# SKELETON_SPEC.md - Đặc Tả Kỹ Thuật Bước Dựng Khung (Skeleton)

Tài liệu này lưu trữ đặc tả chi tiết cho giai đoạn đầu: Dựng khung skeleton hoàn chỉnh, chưa tích hợp Google thật và chưa tích hợp RAG thật.

---

## 1. Cấu Trúc Thư Mục

```
tro-ly-van-phong/
├── AGENTS.md
├── PROGRESS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/
│   └── SKELETON_SPEC.md
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              (FastAPI: /chat, /actions/pending, /actions/{id}/approve|reject)
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── loop.py          (vòng lặp agent: nhận tin nhắn -> gọi LLM -> gọi tool/phân quyền)
│   │   │   └── llm.py           (interface LLMClient + FakeLLM trả lời có kịch bản để test)
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── registry.py      (đăng ký tool kèm risk: read | reversible | confirm)
│   │   │   ├── email.py         (search_email, create_draft, send_email -> dùng MockEmailProvider)
│   │   │   ├── calendar.py      (list_events, create_event -> mock)
│   │   │   └── sheets.py        (read_range, update_cells, delete_rows -> mock dry-run)
│   │   ├── confirm/
│   │   │   ├── __init__.py
│   │   │   └── service.py       (tạo pending_action, preview, approve, reject, TTL 10 phút, chống duyệt trùng)
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   └── retriever.py     (interface Retriever + stub trả về danh sách rỗng)
│   │   └── db.py                (SQLite: bảng pending_actions, audit_log)
│   └── tests/
│       ├── __init__.py
│       └── test_confirm.py      (unit tests cho confirm service)
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── App.tsx
        ├── index.css
        └── components/
            ├── Chat.tsx         (màn hình chat)
            ├── ConfirmCard.tsx  (thẻ Cần xác nhận: preview + Duyệt / Sửa / Hủy)
            └── Toast.tsx
```

---

## 2. 4 Kịch Bản Hoạt Động (FakeLLM + Mock)

1. **Kịch bản 1 (Read - tức thì)**:
   - User gõ: `tìm email của Minh`
   - FakeLLM sinh tool call `search_email(query="Minh")`
   - Tool có rủi ro `read` -> thực thi ngay lập tức, trả danh sách kết quả giả lập hiển thị trên màn hình chat.

2. **Kịch bản 2 (Confirm - email)**:
   - User gõ: `gửi email cho Minh nội dung ...`
   - FakeLLM sinh tool call `send_email(to="minh@example.com", subject=..., body=...)`
   - Tool có rủi ro `confirm` -> **KHÔNG** gửi ngay; tạo `pending_action`, trả về thẻ "Cần xác nhận" chứa preview To/Tiêu đề/Nội dung.

3. **Kịch bản 3 (Duyệt / Hủy)**:
   - Bấm **Duyệt**: Gửi `POST /actions/{id}/approve` -> Mock email được "gửi" và ghi vào `audit_log`.
   - Bấm **Hủy**: Gửi `POST /actions/{id}/reject` -> Trạng thái đổi thành `REJECTED`, không thực thi hành động.
   - Bấm **Sửa**: Frontend hiện toast thông báo *"Chức năng đang phát triển"*. Backend hỗ trợ tham số `edited_args` trong endpoint `/approve`.

4. **Kịch bản 4 (Dry-run - xóa dữ liệu sheet)**:
   - User gõ: `xóa 10 dòng đầu sheet Doanh thu`
   - FakeLLM sinh tool call `delete_rows(sheet_name="Doanh thu", count=10)`
   - Chạy hàm `dry_run` -> sinh preview (số dòng bị xóa, dữ liệu mẫu của các dòng sắp xóa) và chuyển sang chờ xác nhận.

---

## 3. Yêu Cầu Kỹ Thuật Đặc Biệt

- **Chống duyệt đúp (Idempotency)**: Nếu gọi `approve` hai lần, lần thứ hai phải báo đã duyệt hoặc trả kết quả cũ mà không gọi lại tool.
- **TTL 10 phút**: Sau 10 phút kể từ lúc tạo, nếu gọi `approve` thì bị từ chối với lỗi hết hạn.
- **Hỗ trợ `edited_args`**: Endpoint `/actions/{id}/approve` nhận tham số tùy chọn `edited_args`. Khi có, backend validate và thực thi với tham số này, đồng thời ghi cả `original_args` và `edited_args` vào `audit_log`.
