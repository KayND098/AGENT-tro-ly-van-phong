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

def get_web_client_credentials() -> tuple[str, str]:
    """
    Đọc client_id và client_secret từ GOOGLE_WEB_CLIENT_FILE (không lưu secret trong DB).
    Tuyệt đối không log secret ra console hay log file.
    """
    client_file = get_web_client_file()
    if not client_file.exists():
        return "", ""
    try:
        import json
        with open(client_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = data.get("web") or data.get("installed") or {}
        return str(cfg.get("client_id", "") or ""), str(cfg.get("client_secret", "") or "")
    except Exception:
        return "", ""

def get_token_encryption_key() -> str:
    """Khóa Fernet 32-byte base64 để mã hóa/giải mã token Google Workspace."""
    return os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()

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

def get_auth_mode() -> str:
    """
    Trả về 'google' hoặc 'demo'.
    Mặc định an toàn là 'google'. Không bao giờ tự bật demo khi thiếu hoặc sai giá trị.
    """
    mode = os.getenv("AUTH_MODE", "google").strip().lower()
    return "demo" if mode == "demo" else "google"

def is_demo_mode() -> bool:
    return get_auth_mode() == "demo"

def validate_demo_mode_or_raise() -> None:
    """
    Kiểm tra ràng buộc an toàn cho chế độ demo:
    - Từ chối khởi động nếu APP_BASE_URL bắt đầu bằng https hoặc là tên miền công khai.
    - Demo chỉ dành cho localhost / 127.0.0.1.
    - Ghi cảnh báo log khi demo chạy.
    """
    if not is_demo_mode():
        return
    base = get_app_base_url()
    base_lower = base.lower()
    if base_lower.startswith("https://") or base_lower.startswith("https:"):
        raise RuntimeError(
            "Chế độ demo (AUTH_MODE=demo) không cho phép sử dụng HTTPS hoặc tên miền công khai. "
            "Vui lòng chỉ sử dụng HTTP trên localhost (ví dụ: http://localhost:5173)."
        )
    from urllib.parse import urlparse
    parsed = urlparse(base)
    hostname = (parsed.hostname or "").lower()
    allowed_demo_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "backend", "frontend", ""}
    if hostname not in allowed_demo_hosts:
        raise RuntimeError(
            f"Chế độ demo chỉ dành cho localhost, từ chối chạy với tên miền '{hostname}'. "
            "Vui lòng cấu hình AUTH_MODE=google cho môi trường công khai."
        )
    import logging
    logging.getLogger(__name__).warning(
        "⚠️  CẢNH BÁO AN TOÀN: Đang chạy ở CHẾ ĐỘ DEMO (AUTH_MODE=demo). "
        "Dữ liệu mẫu, không kết nối Gmail, tự động đăng nhập người dùng Demo."
    )

