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
    """Tạo bảng users và sessions nếu chưa có (idempotent)."""
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

            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
        """)
        conn.commit()


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
