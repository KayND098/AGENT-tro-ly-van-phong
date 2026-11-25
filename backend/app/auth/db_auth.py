"""
backend/app/auth/db_auth.py
Các hàm DB cho bảng users và sessions.
Khởi tạo idempotent, không phụ thuộc vào db.py gốc ngoài get_db / init_db.
"""
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from ..db import get_db, get_db_path

logger = logging.getLogger(__name__)


def init_auth_tables(db_path: Optional[str] = None) -> None:
    """Tạo bảng users, sessions và user_google_tokens nếu chưa có (idempotent)."""
    path = db_path or get_db_path()
    with get_db(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                google_sub TEXT UNIQUE NOT NULL,
                email    TEXT NOT NULL,
                name     TEXT NOT NULL,
                picture  TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id_hash  TEXT PRIMARY KEY,
                user_id  INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS user_google_tokens (
                user_id       INTEGER PRIMARY KEY,
                access_token  TEXT NOT NULL,
                refresh_token TEXT,
                token_uri     TEXT,
                client_id     TEXT,
                scopes        TEXT NOT NULL,
                expiry        TEXT,
                updated_at    TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_user_google_tokens_user_id ON user_google_tokens(user_id);
        """)

        # Migration idempotent: Xóa cột client_secret khỏi user_google_tokens nếu còn tồn tại
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user_google_tokens)")
        token_cols = [r["name"] for r in cursor.fetchall()]
        if "client_secret" in token_cols:
            try:
                cursor.execute("ALTER TABLE user_google_tokens DROP COLUMN client_secret;")
                conn.commit()
            except Exception:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _user_google_tokens_temp (
                        user_id       INTEGER PRIMARY KEY,
                        access_token  TEXT NOT NULL,
                        refresh_token TEXT,
                        token_uri     TEXT,
                        client_id     TEXT,
                        scopes        TEXT NOT NULL,
                        expiry        TEXT,
                        updated_at    TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                    );
                """)
                cursor.execute("""
                    INSERT INTO _user_google_tokens_temp (user_id, access_token, refresh_token, token_uri, client_id, scopes, expiry, updated_at)
                    SELECT user_id, access_token, refresh_token, token_uri, client_id, scopes, expiry, updated_at FROM user_google_tokens;
                """)
                cursor.execute("DROP TABLE user_google_tokens;")
                cursor.execute("ALTER TABLE _user_google_tokens_temp RENAME TO user_google_tokens;")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_google_tokens_user_id ON user_google_tokens(user_id);")
                conn.commit()

        # Migration: Xử lý dữ liệu token cũ dạng plaintext (mã hóa lại nếu có key, xóa nếu không có key hoặc hỏng)
        try:
            from .crypto import encrypt_token, TokenEncryptionError
            rows = conn.execute("SELECT user_id, access_token, refresh_token FROM user_google_tokens").fetchall()
            for r in rows:
                uid = r["user_id"]
                acc = r["access_token"]
                ref = r["refresh_token"]
                if acc and not acc.startswith("gAAAAA"):
                    try:
                        enc_acc = encrypt_token(acc)
                        enc_ref = encrypt_token(ref) if (ref and not ref.startswith("gAAAAA")) else ref
                        conn.execute("UPDATE user_google_tokens SET access_token = ?, refresh_token = ? WHERE user_id = ?", (enc_acc, enc_ref, uid))
                    except TokenEncryptionError:
                        conn.execute("DELETE FROM user_google_tokens WHERE user_id = ?", (uid,))
            conn.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def upsert_user(
    google_sub: str,
    email: str,
    name: str,
    picture: Optional[str],
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Tạo hoặc cập nhật user theo google_sub. Trả về dict user."""
    path = db_path or get_db_path()
    now = datetime.now(timezone.utc).isoformat()
    with get_db(path) as conn:
        conn.execute(
            """
            INSERT INTO users (google_sub, email, name, picture, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(google_sub) DO UPDATE SET
                email      = excluded.email,
                name       = excluded.name,
                picture    = excluded.picture,
                last_login = excluded.last_login
            """,
            (google_sub, email, name, picture, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, google_sub, email, name, picture, created_at, last_login "
            "FROM users WHERE google_sub = ?",
            (google_sub,),
        ).fetchone()
        return dict(row)


def get_user_by_id(user_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    path = db_path or get_db_path()
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT id, google_sub, email, name, picture FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    """SHA-256 hex của token. DB chỉ lưu hash này, không lưu giá trị gốc."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, session_days: int, db_path: Optional[str] = None) -> str:
    """
    Tạo phiên mới. Trả về chuỗi cookie ngẫu nhiên 32 byte (hex, 64 ký tự).
    DB chỉ lưu SHA-256 hash của giá trị đó.
    """
    path = db_path or get_db_path()
    token = secrets.token_hex(32)   # 64 hex chars — chỉ gửi qua cookie, không log
    id_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=session_days)).isoformat()

    with get_db(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (id_hash, user_id, now.isoformat(), expires_at),
        )
        conn.commit()
    return token


def get_session_user(token: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Tra cứu phiên theo token (cookie). Gia hạn tự động nếu còn hạn.
    Trả về dict user hoặc None nếu không tìm thấy / hết hạn.
    """
    path = db_path or get_db_path()
    id_hash = _hash_token(token)
    now = datetime.now(timezone.utc)

    with get_db(path) as conn:
        row = conn.execute(
            "SELECT id_hash, user_id, expires_at FROM sessions WHERE id_hash = ?",
            (id_hash,),
        ).fetchone()
        if not row:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            # Dọn phiên hết hạn
            conn.execute("DELETE FROM sessions WHERE id_hash = ?", (id_hash,))
            conn.commit()
            return None
        # Gia hạn: cộng thêm SESSION_DAYS từ thời điểm hiện tại
        from .config import get_session_days
        new_expires = (now + timedelta(days=get_session_days())).isoformat()
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE id_hash = ?",
            (new_expires, id_hash),
        )
        conn.commit()

    return get_user_by_id(row["user_id"], path)


def delete_session(token: str, db_path: Optional[str] = None) -> None:
    """Xóa phiên khỏi DB (đăng xuất phía server)."""
    path = db_path or get_db_path()
    id_hash = _hash_token(token)
    with get_db(path) as conn:
        conn.execute("DELETE FROM sessions WHERE id_hash = ?", (id_hash,))
        conn.commit()


# ---------------------------------------------------------------------------
# Google Workspace OAuth Token helpers (Per-User)
# Tuyệt đối không log access_token, refresh_token hoặc client_secret
# ---------------------------------------------------------------------------

def upsert_user_google_token(
    user_id: int,
    access_token: str,
    refresh_token: Optional[str] = None,
    token_uri: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    scopes: str = "",
    expiry: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lưu hoặc cập nhật OAuth token Google Workspace cho user_id cụ thể.
    - access_token và refresh_token BẮT BUỘC được mã hóa bằng Fernet qua biến TOKEN_ENCRYPTION_KEY.
    - Thiếu hoặc sai khóa -> raise TokenEncryptionError (từ chối lưu dạng thường).
    - TUYỆT ĐỐI KHÔNG lưu client_secret vào DB.
    - Giữ lại refresh_token cũ nếu giá trị mới là None (tránh mất refresh token).
    """
    from .crypto import encrypt_token

    # Mã hóa bắt buộc trước khi lưu vào DB
    enc_access_token = encrypt_token(access_token)
    enc_refresh_token = encrypt_token(refresh_token) if refresh_token else None

    init_auth_tables(db_path)
    path = db_path or get_db_path()
    now = datetime.now(timezone.utc).isoformat()
    with get_db(path) as conn:
        conn.execute(
            """
            INSERT INTO user_google_tokens (
                user_id, access_token, refresh_token, token_uri, client_id, scopes, expiry, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, user_google_tokens.refresh_token),
                token_uri     = COALESCE(excluded.token_uri, user_google_tokens.token_uri),
                client_id     = COALESCE(excluded.client_id, user_google_tokens.client_id),
                scopes        = excluded.scopes,
                expiry        = excluded.expiry,
                updated_at    = excluded.updated_at
            """,
            (user_id, enc_access_token, enc_refresh_token, token_uri, client_id, scopes, expiry, now),
        )
        conn.commit()

    return {
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_uri": token_uri,
        "client_id": client_id,
        "scopes": scopes,
        "expiry": expiry,
        "updated_at": now,
    }


def get_user_google_token(user_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Lấy Google OAuth token của user_id nếu có.
    Tự động giải mã access_token và refresh_token bằng Fernet.
    Nếu giải mã thất bại (sai key, dữ liệu hỏng hoặc plaintext cũ) -> xóa bản ghi hỏng và trả về None.
    Tuyệt đối không trả client_secret.
    """
    init_auth_tables(db_path)
    path = db_path or get_db_path()
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT user_id, access_token, refresh_token, token_uri, client_id, scopes, expiry, updated_at "
            "FROM user_google_tokens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)

        from .crypto import decrypt_token
        dec_access = decrypt_token(d["access_token"])
        if not dec_access:
            # Giải mã thất bại: sai key hoặc dữ liệu plaintext cũ không giải mã được -> xóa bản ghi để bảo vệ
            conn.execute("DELETE FROM user_google_tokens WHERE user_id = ?", (user_id,))
            conn.commit()
            logger.warning("Token của user_id=%s không thể giải mã, đã xóa bản ghi để bảo mật.", user_id)
            return None

        d["access_token"] = dec_access
        if d.get("refresh_token"):
            dec_refresh = decrypt_token(d["refresh_token"])
            d["refresh_token"] = dec_refresh

        return d


def delete_user_google_token(user_id: int, db_path: Optional[str] = None) -> None:
    """Xóa Google OAuth token của user_id (ngắt kết nối Google Workspace)."""
    init_auth_tables(db_path)
    path = db_path or get_db_path()
    with get_db(path) as conn:
        conn.execute("DELETE FROM user_google_tokens WHERE user_id = ?", (user_id,))
        conn.commit()


def get_or_create_demo_user(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Lấy hoặc tạo người dùng Demo cố định (chế độ AUTH_MODE=demo).
    Dữ liệu gắn với user_id của người dùng Demo trong bảng users.
    """
    init_auth_tables(db_path)
    return upsert_user(
        google_sub="demo_sub_001",
        email="demo@office-assistant.local",
        name="Demo",
        picture=None,
        db_path=db_path,
    )


