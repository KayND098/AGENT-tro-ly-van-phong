# AGENTS.md - Quy tắc và Chuẩn mực Hoạt động của Trợ lý Văn phòng AI

Tài liệu này là luật chung và tiêu chuẩn kiến trúc cho toàn bộ dự án **Trợ lý Văn phòng AI (Office Assistant)**. Mọi phiên làm việc của AI Agent và lập trình viên đều phải tuân thủ nghiêm ngặt các quy tắc dưới đây.

---

## 1. Nguyên Tắc Cốt Lõi (Core Principles)

1. **An toàn là trên hết (Safety First)**:
   - Tuyệt đối không tự ý thực thi các tác vụ gây thay đổi vĩnh viễn, phát tán thông tin ra bên ngoài hoặc xóa dữ liệu mà không có sự xác nhận của người dùng.
   - Không tin tưởng mù quáng vào output của LLM. Mọi tham số truyền vào công cụ tác động ra ngoài đều phải được kiểm định (validation).

2. **Human-in-the-Loop (Người dùng kiểm soát)**:
   - Với các hành vi có rủi ro, hệ thống chỉ chuẩn bị trạng thái "chờ duyệt" (Pending Action) kèm **bản xem trước (Preview)** hoặc **chạy thử không ghi (Dry-run)** rõ ràng.
   - Người dùng có quyền: **Duyệt (Approve)**, **Sửa (Edit)**, hoặc **Hủy (Reject)**.

3. **Tính Bất biến & Chống trùng lặp (Idempotency & One-Time Execution)**:
   - Mỗi lệnh chờ duyệt chỉ được phép thực thi đúng **một lần duy nhất**.
   - Nếu người dùng bấm duyệt 2 lần (hoặc có race condition mạng), backend chỉ chạy 1 lần và trả về kết quả đã thực thi.

4. **Thời hạn hiệu lực (TTL - Time to Live)**:
   - Mọi Pending Action có thời hạn sống tối đa là **10 phút**. Quá thời gian này, lệnh chuyển sang trạng thái `EXPIRED` và không được phép duyệt nữa.

5. **Ghi vết kiểm toán (Audit Trail)**:
   - Mọi hành động được thực thi, duyệt, từ chối hoặc hết hạn đều phải ghi nhận vào bảng `audit_log` với đầy đủ timestamp, tham số gốc (`original_args`), tham số điều chỉnh nếu có (`edited_args`), và kết quả thực thi.

---

## 2. Phân Loại Rủi Ro Công Cụ (Tool Risk Levels)

| Mức độ | Định nghĩa | Hành vi hệ thống | Ví dụ công cụ |
|---|---|---|---|
| `read` | Đọc hoặc tìm kiếm dữ liệu, không làm thay đổi trạng thái | **Thực thi ngay lập tức**, trả kết quả cho Agent tổng hợp | `search_email`, `list_events`, `read_sheet_range` |
| `reversible` | Tạo bản nháp, thay đổi có thể hoàn tác ngay mà không ảnh hưởng người khác | Thực thi kèm thông báo cách hoàn tác hoặc tạo nháp | `create_draft_email`, `stage_calendar_event` |
| `confirm` | Gửi email ra ngoài, xóa hàng loạt dữ liệu, ghi đè sheet, hủy sự kiện | **Tạo Pending Action + Preview/Dry-run**, dừng vòng lặp chờ duyệt | `send_email`, `delete_sheet_rows`, `update_cells` |

---

## 3. Quy Trình Vòng Lặp Agent (Agent Execution Loop)

```
[Tin nhắn Người dùng]
         │
         ▼
[Agent Loop + FakeLLM / LLM]
         │
         ├──> [Quyết định gọi Tool]
         │           │
         │           ├── Risk = 'read' ────────> [Chạy Tool ngay] ──> [Trả kết quả]
         │           │
         │           └── Risk = 'confirm' ────> [Tạo Pending Action]
         │                                            │
         │                                     [Sinh Preview / Dry-run]
         │                                            │
         │                                            ▼
         │                               [Trả Thẻ "Cần xác nhận"]
         ▼
[Người dùng tương tác]
   ├── [Hủy]   ──> Chuyển status = REJECTED, ghi audit_log
   ├── [Sửa]   ──> Cung cấp edited_args, validate lại schema
   └── [Duyệt] ──> Kiểm tra TTL (10p) + Lock chống duyệt đúp
                       │
                       ▼
                 [Thực thi Tool thật / Mock Provider]
                       │
                       ▼
                 [Ghi audit_log & Cập nhật status = APPROVED]
```

---

## 4. Quy Ước Kiến Trúc Dự Án

- **Backend**:
  - Viết bằng FastAPI (Python 3.10+).
  - Tách bạch các layer: `agent/` (điều phối vòng lặp, interface LLM), `tools/` (registry và logic nghiệp vụ), `confirm/` (quản lý trạng thái pending action), `db.py` (SQLite schema & audit trail), `rag/` (retriever interface).
  - Tách Provider: Tool nghiệp vụ gọi qua Interface Provider (như `MockEmailProvider` hiện tại, sau này hoán đổi sang `GoogleWorkspaceProvider` mà không sửa core logic).
- **Frontend**:
  - React + TypeScript + Vite.
  - UI tối giản, trực quan, hỗ trợ thẻ xác nhận riêng biệt với màu sắc cảnh báo rõ ràng.
- **Testing**:
  - Đảm bảo 100% các case xác nhận bảo mật được test: không chạy khi chưa duyệt, duyệt đúp chỉ chạy 1 lần, quá hạn 10 phút bị từ chối, và hỗ trợ `edited_args`.
