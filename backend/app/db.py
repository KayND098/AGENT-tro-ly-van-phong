import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Generator

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")

def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)

def create_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    conn = create_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()

# Giữ tương thích ngược với get_connection
get_connection = get_db

def init_db(db_path: Optional[str] = None) -> None:
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with get_db(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                tool_name TEXT NOT NULL,
                original_args TEXT NOT NULL,
                edited_args TEXT,
                preview TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_id TEXT,
                action_type TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                original_args TEXT NOT NULL,
                edited_args TEXT,
                result TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        # Migration idempotent cho DB đã tồn tại: thêm cột user_id nếu chưa có
        cursor.execute("PRAGMA table_info(pending_actions)")
        pending_cols = [row["name"] for row in cursor.fetchall()]
        if "user_id" not in pending_cols:
            cursor.execute("ALTER TABLE pending_actions ADD COLUMN user_id INTEGER;")

        cursor.execute("PRAGMA table_info(audit_log)")
        audit_cols = [row["name"] for row in cursor.fetchall()]
        if "user_id" not in audit_cols:
            cursor.execute("ALTER TABLE audit_log ADD COLUMN user_id INTEGER;")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_actions(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_user_id ON pending_actions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action_id ON audit_log(action_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_log(user_id);")
        conn.commit()

def record_audit_log(
    action_type: str,
    tool_name: str,
    original_args: Dict[str, Any],
    status: str,
    action_id: Optional[str] = None,
    edited_args: Optional[Dict[str, Any]] = None,
    result: Optional[Any] = None,
    user_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    init_db(db_path)  # idempotent: đảm bảo bảng tồn tại trước khi ghi
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (user_id, action_id, action_type, tool_name, original_args, edited_args, result, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                action_id,
                action_type,
                tool_name,
                json.dumps(original_args, ensure_ascii=False),
                json.dumps(edited_args, ensure_ascii=False) if edited_args is not None else None,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                status,
                now_iso,
            ),
        )
        conn.commit()
        return cursor.lastrowid

