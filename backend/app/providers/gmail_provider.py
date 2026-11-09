import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Quyền tối thiểu: Chỉ đọc Gmail (gmail.readonly)
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [GMAIL_READONLY_SCOPE]

# Thư mục gốc backend và secrets
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SECRETS_DIR = BACKEND_DIR / "secrets"
DEFAULT_CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"
DEFAULT_TOKEN_FILE = SECRETS_DIR / "token.json"


def sanitize_sensitive_data(text: str) -> str:
    """
    Loại bỏ các thông tin nhạy cảm (token, mã xác thực, client secret, bearer) khỏi log và thông báo lỗi.
    Tuyệt đối không để lộ token ra bên ngoài.
    """
    if not text:
        return ""
    # Mask OAuth access tokens (thường bắt đầu bằng ya29...)
    text = re.sub(r'ya29\.[a-zA-Z0-9_\-]+', '[REDACTED_ACCESS_TOKEN]', text)
    # Mask OAuth refresh tokens (thường bắt đầu bằng 1//...)
    text = re.sub(r'1//[a-zA-Z0-9_\-]+', '[REDACTED_REFRESH_TOKEN]', text)
    # Mask Authorization header / Bearer token
    text = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [REDACTED_TOKEN]', text, flags=re.IGNORECASE)
    # Mask Client Secret
    text = re.sub(r'GOCSPX-[a-zA-Z0-9_\-]+', '[REDACTED_CLIENT_SECRET]', text)
    text = re.sub(r'client_secret=[a-zA-Z0-9_\-\.]+', 'client_secret=[REDACTED_SECRET]', text, flags=re.IGNORECASE)
    text = re.sub(r'access_token=[a-zA-Z0-9_\-\.]+', 'access_token=[REDACTED_TOKEN]', text, flags=re.IGNORECASE)
    return text


class GmailProvider:
    """
    GmailProvider kết nối với Google Workspace Gmail API (CHỈ ĐỌC).
    Cùng interface với MockEmailProvider.
    """

    def __init__(
        self,
        client_secret_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        service: Optional[Any] = None,
    ):
        self.client_secret_path = client_secret_path or DEFAULT_CLIENT_SECRET_FILE
        self.token_path = token_path or DEFAULT_TOKEN_FILE
        self.scopes = SCOPES
        self.service = service

    def is_ready(self) -> bool:
        """
        Kiểm tra xem provider đã có đủ điều kiện để hoạt động hay chưa:
        - Đã inject service trực tiếp (dùng cho testing/mock)
        - Hoặc tồn tại cả client_secret_path và token_path (đã đăng nhập qua google_login.py)
        """
        if self.service is not None:
            return True
        return (
            self.client_secret_path.exists()
            and self.token_path.exists()
            and self.token_path.stat().st_size > 0
        )

    def _get_service(self):
        """
        Khởi tạo hoặc trả về Google API Resource cho Gmail.
        Tự động làm mới (refresh) token nếu token hết hạn nhưng còn refresh_token.
        """
        if self.service is not None:
            return self.service

        if not self.token_path.exists():
            logger.warning(
                "Không tìm thấy file token tại %s. Vui lòng chạy backend/google_login.py để đăng nhập.",
                self.token_path,
            )
            return None

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)

            # Tự động làm mới token nếu đã hết hạn và có refresh_token
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Lưu lại token đã làm mới vào file
                    with open(self.token_path, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                    logger.info("Đã tự động làm mới Gmail token thành công.")
                except Exception as refresh_err:
                    clean_err = sanitize_sensitive_data(str(refresh_err))
                    logger.exception("Không thể làm mới token Gmail: %s", clean_err)
                    return None

            if not creds or not creds.valid:
                logger.warning("Token Gmail không hợp lệ hoặc đã hết hạn mà không thể làm mới.")
                return None

            self.service = build("gmail", "v1", credentials=creds)
            return self.service
        except Exception as exc:
            clean_err = sanitize_sensitive_data(str(exc))
            logger.exception("Lỗi khi khởi tạo dịch vụ Gmail API: %s", clean_err)
            return None

    def search_email(self, query: str) -> List[Dict[str, Any]]:
        """
        Tìm kiếm email trong Gmail với cú pháp tìm kiếm của Gmail.
        Giới hạn tối đa 10 thư, chỉ lấy người gửi, người nhận, tiêu đề, ngày, và snippet.
        """
        service = self._get_service()
        if not service:
            raise RuntimeError("Dịch vụ Gmail chưa sẵn sàng hoặc chưa đăng nhập thành công.")

        try:
            # Truy vấn theo cú pháp tìm kiếm của Gmail, tối đa 10 thư
            response = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=10,
            ).execute()

            messages = response.get("messages", [])
            if not messages:
                return []

            results = []
            for msg_item in messages:
                msg_id = msg_item.get("id")
                if not msg_id:
                    continue

                # Chỉ lấy metadata headers và đoạn trích ngắn (snippet), không lấy body đầy đủ
                msg_detail = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()

                headers_list = msg_detail.get("payload", {}).get("headers", [])
                headers = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

                sender = headers.get("from", "Không rõ người gửi")
                recipient = headers.get("to", "")
                subject = headers.get("subject", "(Không có tiêu đề)")
                date_str = headers.get("date", "")
                snippet = msg_detail.get("snippet", "")

                results.append({
                    "id": msg_id,
                    "from": sender,
                    "to": recipient,
                    "subject": subject,
                    "body": snippet,
                    "date": date_str,
                })

            return results
        except Exception as exc:
            clean_err = sanitize_sensitive_data(str(exc))
            logger.exception("Lỗi khi tìm kiếm email trên Gmail API: %s", clean_err)
            raise RuntimeError(f"Lỗi khi tìm kiếm email trên Gmail: {clean_err}") from None

    def create_draft(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Phiên 1 chỉ hỗ trợ đọc email. Tác vụ tạo nháp tạm thời ủy quyền cho mock."""
        from app.tools.email import mock_email_provider
        return mock_email_provider.create_draft(to=to, subject=subject, body=body)

    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Phiên 1 chỉ hỗ trợ đọc email. Tác vụ gửi email tạm thời ủy quyền cho mock."""
        from app.tools.email import mock_email_provider
        return mock_email_provider.send_email(to=to, subject=subject, body=body)
