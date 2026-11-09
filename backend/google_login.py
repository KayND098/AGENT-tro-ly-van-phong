import sys
from pathlib import Path

# Đường dẫn tuyệt đối tới thư mục backend và secrets
BACKEND_DIR = Path(__file__).resolve().parent
SECRETS_DIR = BACKEND_DIR / "secrets"
CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"
TOKEN_FILE = SECRETS_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def login() -> bool:
    """
    Thực hiện đăng nhập OAuth 2.0 kiểu Desktop App (InstalledAppFlow)
    để cấp quyền đọc Gmail (gmail.readonly) và lưu token vào backend/secrets/token.json.
    """
    if not CLIENT_SECRET_FILE.exists():
        print(f"Lỗi: Không tìm thấy file client_secret.json tại: {CLIENT_SECRET_FILE}")
        print("Vui lòng tải credentials (OAuth 2.0 Client ID loại Desktop App) từ Google Cloud Console và đặt vào đường dẫn trên.")
        return False

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_FILE),
            scopes=SCOPES,
        )
        # Mở trình duyệt trên localhost để người dùng đăng nhập
        creds = flow.run_local_server(port=0)

        # Lưu token vào token.json - Tuyệt đối không log nội dung token
        with open(TOKEN_FILE, "w", encoding="utf-8") as token_out:
            token_out.write(creds.to_json())

        print(f"Đăng nhập thành công! Token đã được lưu an toàn tại: {TOKEN_FILE}")
        return True
    except Exception as exc:
        print(f"Đăng nhập thất bại: {type(exc).__name__}")
        return False

if __name__ == "__main__":
    login()
