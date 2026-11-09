import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from .registry import registry, RiskLevel

logger = logging.getLogger(__name__)

# Nạp .env nếu chưa nạp (để EMAIL_PROVIDER có hiệu lực)
from dotenv import load_dotenv
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_env_path = _BACKEND_DIR / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    _root_env = _BACKEND_DIR.parent / ".env"
    if _root_env.exists():
        load_dotenv(dotenv_path=_root_env)


class MockEmailProvider:
    """Provider giả lập dùng dữ liệu in-memory để kiểm thử và phát triển."""

    def __init__(self):
        self.inbox = [
            {
                "id": "msg_001",
                "from": "minh.nguyen@company.com",
                "to": "me@company.com",
                "subject": "Báo cáo doanh thu quý 3",
                "body": "Chào anh, em gửi báo cáo doanh thu quý 3 đính kèm trong sheet Doanh thu nhé.",
                "date": "2026-10-30 09:30:00",
            },
            {
                "id": "msg_002",
                "from": "minh.nguyen@company.com",
                "to": "me@company.com",
                "subject": "Lịch họp dự án tuần tới",
                "body": "Anh xem sắp xếp họp thảo luận về tính năng xác nhận an toàn vào sáng thứ Tư nhé.",
                "date": "2026-11-01 14:15:00",
            },
            {
                "id": "msg_003",
                "from": "lan.tran@company.com",
                "to": "me@company.com",
                "subject": "Yêu cầu tài liệu quy trình",
                "body": "Nhờ anh chia sẻ tài liệu quy trình vận hành mới nhất.",
                "date": "2026-11-02 11:00:00",
            },
        ]
        self.drafts = []
        self.sent = []

    def search_email(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower()
        results = []
        for msg in self.inbox + self.sent:
            if (
                q in msg["from"].lower()
                or q in msg["to"].lower()
                or q in msg["subject"].lower()
                or q in msg["body"].lower()
            ):
                results.append(msg)
        return results

    def create_draft(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        draft_id = f"draft_{len(self.drafts) + 1:03d}"
        draft = {
            "id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "status": "draft",
        }
        self.drafts.append(draft)
        return {"success": True, "draft_id": draft_id, "message": "Đã tạo thư nháp thành công."}

    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        msg_id = f"sent_{len(self.sent) + 1:03d}"
        msg = {
            "id": msg_id,
            "from": "me@company.com",
            "to": to,
            "subject": subject,
            "body": body,
            "status": "sent",
        }
        self.sent.append(msg)
        return {"success": True, "message_id": msg_id, "status": "sent", "to": to, "subject": subject}


# Instance mock dùng chung – các test truy cập trực tiếp `email.email_provider`
# để kiểm tra trạng thái sent/drafts (tương thích với toàn bộ test cũ)
mock_email_provider = MockEmailProvider()

# Alias giữ tương thích ngược với toàn bộ test cũ
email_provider = mock_email_provider


def get_email_provider():
    """
    Factory: chọn provider theo biến môi trường EMAIL_PROVIDER.
    - EMAIL_PROVIDER=mock (mặc định): dùng MockEmailProvider.
    - EMAIL_PROVIDER=google: thử dùng GmailProvider;
      nếu thiếu client_secret.json hoặc token.json hoặc xảy ra lỗi thì
      tự động fallback về MockEmailProvider kèm cảnh báo thân thiện (không crash).
    """
    provider_name = os.getenv("EMAIL_PROVIDER", "mock").strip().lower()
    if provider_name != "google":
        return mock_email_provider

    # Thử khởi tạo GmailProvider
    try:
        from app.providers.gmail_provider import GmailProvider, DEFAULT_CLIENT_SECRET_FILE, DEFAULT_TOKEN_FILE
        gp = GmailProvider()
        if not DEFAULT_CLIENT_SECRET_FILE.exists():
            logger.warning(
                "⚠️  EMAIL_PROVIDER=google nhưng không tìm thấy client_secret.json tại '%s'. "
                "Hệ thống tự động sử dụng MockEmailProvider. "
                "Chạy 'python backend/google_login.py' để đăng nhập.",
                DEFAULT_CLIENT_SECRET_FILE,
            )
            return mock_email_provider
        if not DEFAULT_TOKEN_FILE.exists():
            logger.warning(
                "⚠️  EMAIL_PROVIDER=google nhưng chưa có token.json tại '%s'. "
                "Hệ thống tự động sử dụng MockEmailProvider. "
                "Chạy 'python backend/google_login.py' để đăng nhập.",
                DEFAULT_TOKEN_FILE,
            )
            return mock_email_provider
        logger.info("GmailProvider đã sẵn sàng (scope: gmail.readonly).")
        return gp
    except ImportError as exc:
        logger.warning(
            "⚠️  Không thể import GmailProvider (%s). Fallback về MockEmailProvider.",
            str(exc),
        )
        return mock_email_provider
    except Exception as exc:
        logger.warning(
            "⚠️  Lỗi khi khởi tạo GmailProvider (%s: %s). Fallback về MockEmailProvider.",
            type(exc).__name__,
            str(exc),
        )
        return mock_email_provider


def search_email_handler(query: str) -> Dict[str, Any]:
    """
    Handler tìm kiếm email.
    Dùng provider chọn theo EMAIL_PROVIDER. Lỗi API trả thông báo thân thiện, không crash.
    Nội dung trả về được vòng lặp Agent đánh dấu là DỮ LIỆU (cơ chế hiện tại giữ nguyên).
    """
    provider = get_email_provider()
    try:
        emails = provider.search_email(query=query)
        return {"query": query, "count": len(emails), "emails": emails}
    except Exception as exc:
        # Ghi log không kèm token; trả thông báo thân thiện
        logger.exception("Lỗi khi tìm kiếm email qua %s: %s", type(provider).__name__, type(exc).__name__)
        return {
            "query": query,
            "count": 0,
            "emails": [],
            "error": "Không thể tìm kiếm email lúc này. Vui lòng thử lại hoặc kiểm tra kết nối tài khoản Google.",
        }


def create_draft_handler(to: str, subject: str, body: str) -> Dict[str, Any]:
    return mock_email_provider.create_draft(to=to, subject=subject, body=body)


def send_email_handler(to: str, subject: str, body: str) -> Dict[str, Any]:
    return mock_email_provider.send_email(to=to, subject=subject, body=body)


def send_email_preview(to: str, subject: str, body: str) -> Dict[str, Any]:
    return {
        "title": "Xác nhận gửi Email",
        "action_type": "send_email",
        "to": to,
        "subject": subject,
        "body": body,
        "warning": "Email sẽ được gửi chính thức đến hộp thư của người nhận.",
    }


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------
registry.register(
    name="search_email",
    description="Tìm kiếm email theo từ khóa người gửi, người nhận, tiêu đề hoặc nội dung.",
    risk_level=RiskLevel.READ,
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Từ khóa tìm kiếm"}},
        "required": ["query"],
    },
    execute_fn=search_email_handler,
)

registry.register(
    name="create_draft",
    description="Tạo bản nháp email mà không gửi đi.",
    risk_level=RiskLevel.REVERSIBLE,
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Địa chỉ người nhận"},
            "subject": {"type": "string", "description": "Tiêu đề email"},
            "body": {"type": "string", "description": "Nội dung email"},
        },
        "required": ["to", "subject", "body"],
    },
    execute_fn=create_draft_handler,
)

registry.register(
    name="send_email",
    description="Gửi email chính thức tới người nhận (yêu cầu xác nhận).",
    risk_level=RiskLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Địa chỉ người nhận"},
            "subject": {"type": "string", "description": "Tiêu đề email"},
            "body": {"type": "string", "description": "Nội dung email"},
        },
        "required": ["to", "subject", "body"],
    },
    execute_fn=send_email_handler,
    dry_run_fn=send_email_preview,
)
