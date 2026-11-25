import logging
import re
from datetime import datetime, timezone
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
    Hỗ trợ khởi tạo từ DB token của user_id hoặc fallback file secrets/token.json.
    """

    def __init__(
        self,
        client_secret_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        service: Optional[Any] = None,
        token_data: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        self.client_secret_path = client_secret_path or DEFAULT_CLIENT_SECRET_FILE
        self.token_path = token_path or DEFAULT_TOKEN_FILE
        self.scopes = SCOPES
        self.service = service
        self.token_data = token_data
        self.user_id = user_id

    def is_ready(self) -> bool:
        """
        Kiểm tra xem provider đã có đủ điều kiện để hoạt động hay chưa:
        - Đã inject service trực tiếp (dùng cho testing/mock)
        - Có token_data hợp lệ từ DB
        - Hoặc tồn tại cả client_secret_path và token_path (file chung)
        """
        if self.service is not None:
            return True
        if self.token_data is not None and self.token_data.get("access_token"):
            return True
        return (
            self.client_secret_path.exists()
            and self.token_path.exists()
            and self.token_path.stat().st_size > 0
        )

    def _get_service(self):
        """
        Khởi tạo hoặc trả về Google API Resource cho Gmail.
        Tự động làm mới (refresh) token nếu token hết hạn nhưng còn refresh_token,
        và cập nhật lại access_token + expiry mới vào DB (nếu có user_id) hoặc file.
        """
        if self.service is not None:
            return self.service

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = None
            if self.token_data is not None:
                # Khởi tạo Credentials từ DB token
                expiry = None
                if self.token_data.get("expiry"):
                    try:
                        expiry_dt = datetime.fromisoformat(self.token_data["expiry"])
                        if expiry_dt.tzinfo is not None:
                            expiry_dt = expiry_dt.astimezone(timezone.utc).replace(tzinfo=None)
                        expiry = expiry_dt
                    except Exception:
                        pass

                scopes_val = self.token_data.get("scopes") or SCOPES
                if isinstance(scopes_val, str):
                    scopes_val = scopes_val.split()

                from app.auth.config import get_web_client_credentials
                web_client_id, web_client_secret = get_web_client_credentials()

                creds = Credentials(
                    token=self.token_data.get("access_token"),
                    refresh_token=self.token_data.get("refresh_token"),
                    token_uri=self.token_data.get("token_uri") or "https://oauth2.googleapis.com/token",
                    client_id=web_client_id or self.token_data.get("client_id"),
                    client_secret=web_client_secret,
                    scopes=scopes_val,
                    expiry=expiry,
                )
            elif self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
            else:
                logger.warning("Không tìm thấy thông tin token cho Gmail.")
                return None

            # Tự động làm mới token nếu đã hết hạn và có refresh_token
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Cập nhật lại token đã làm mới vào DB hoặc file
                    if self.user_id is not None:
                        from app.auth.db_auth import upsert_user_google_token
                        expiry_iso = creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else None
                        scopes_str = " ".join(creds.scopes) if isinstance(creds.scopes, (list, tuple, set)) else str(creds.scopes or "")
                        upsert_user_google_token(
                            user_id=self.user_id,
                            access_token=creds.token or "",
                            refresh_token=creds.refresh_token,
                            token_uri=getattr(creds, "token_uri", None),
                            client_id=getattr(creds, "client_id", None) or web_client_id,
                            scopes=scopes_str,
                            expiry=expiry_iso,
                        )
                        logger.info("Đã tự động làm mới và cập nhật Gmail token cho user_id=%s vào DB.", self.user_id)
                    elif self.token_path.exists():
                        with open(self.token_path, "w", encoding="utf-8") as f:
                            f.write(creds.to_json())
                        logger.info("Đã tự động làm mới Gmail token file thành công.")
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
