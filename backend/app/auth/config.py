"""
backend/app/auth/config.py
Đọc và chuẩn hóa cấu hình xác thực từ biến môi trường.
Tuyệt đối không log giá trị bí mật.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Nạp .env từ backend/ hoặc gốc dự án
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
for _p in (_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env"):
    if _p.exists():
        load_dotenv(dotenv_path=_p)
        break

# Đường dẫn file client_secret cho Web App (OAuth 2.0 Web Application)
def get_web_client_file() -> Path:
    raw = os.getenv("GOOGLE_WEB_CLIENT_FILE", "")
    if raw:
        return Path(raw).resolve()
    return _BACKEND_DIR / "secrets" / "web_client_secret.json"

def get_app_base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/")

def get_session_days() -> int:
    try:
        return max(1, int(os.getenv("SESSION_DAYS", "30")))
    except ValueError:
        return 30

def get_allowed_emails() -> list[str]:
    """Trả list email được phép. Rỗng = cho mọi người."""
    raw = os.getenv("ALLOWED_EMAILS", "").strip()
    if not raw:
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]

# Scopes chỉ xin danh tính - KHÔNG xin quyền Gmail
IDENTITY_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
