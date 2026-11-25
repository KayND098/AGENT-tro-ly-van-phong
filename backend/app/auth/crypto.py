"""
backend/app/auth/crypto.py
Quản lý mã hóa và giải mã token Google OAuth bằng Fernet (AES-128-CBC + HMAC-SHA256).
Tuyệt đối không lưu token dạng thường và không tự sinh khóa ngẫu nhiên khi thiếu biến môi trường.
"""
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from .config import get_token_encryption_key

logger = logging.getLogger(__name__)


class TokenEncryptionError(Exception):
    """Lỗi cấu hình hoặc thao tác mã hóa / giải mã token."""
    pass


def get_fernet() -> Fernet:
    """
    Khởi tạo đối tượng Fernet từ biến môi trường TOKEN_ENCRYPTION_KEY.
    Nếu thiếu hoặc sai khóa -> raise TokenEncryptionError với thông báo cấu hình rõ ràng.
    """
    key = get_token_encryption_key()
    if not key:
        raise TokenEncryptionError(
            "Lỗi cấu hình bảo mật: Thiếu biến môi trường TOKEN_ENCRYPTION_KEY. "
            "Hệ thống từ chối lưu hoặc giải mã token Google khi chưa có khóa mã hóa."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise TokenEncryptionError(
            f"Lỗi cấu hình bảo mật: TOKEN_ENCRYPTION_KEY không hợp lệ ({type(exc).__name__}). "
            "Khóa phải là chuỗi Fernet base64 32-byte (ví dụ tạo bởi: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")."
        )


def encrypt_token(token: Optional[str]) -> Optional[str]:
    """Mã hóa token thành chuỗi ciphertext Fernet. Trả về None nếu token rỗng."""
    if not token:
        return None
    f = get_fernet()
    try:
        return f.encrypt(token.encode("utf-8")).decode("utf-8")
    except TokenEncryptionError:
        raise
    except Exception as exc:
        raise TokenEncryptionError(f"Không thể mã hóa token: {str(exc)}")


def decrypt_token(cipher_text: Optional[str]) -> Optional[str]:
    """
    Giải mã chuỗi ciphertext Fernet thành plaintext token.
    Nếu cipher_text rỗng, trả về None.
    Nếu dữ liệu bị lỗi, không khớp khóa hoặc không phải định dạng Fernet -> trả về None và ghi log cảnh báo.
    """
    if not cipher_text:
        return None
    f = get_fernet()
    try:
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("Không thể giải mã token: InvalidToken (khóa không khớp hoặc dữ liệu bị giả mạo).")
        return None
    except Exception as exc:
        logger.warning("Lỗi giải mã token: %s", type(exc).__name__)
        return None
