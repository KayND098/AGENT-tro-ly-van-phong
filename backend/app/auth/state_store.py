"""
backend/app/auth/state_store.py
Lưu state OAuth trong bộ nhớ với TTL 10 phút.
Mỗi entry chứa: state, code_verifier (PKCE), nonce.
Tuyệt đối không log giá trị state, nonce hay code_verifier.
"""
import secrets
import threading
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

_STATE_TTL_SECONDS = 600  # 10 phút
_store: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prune() -> None:
    """Dọn các entry hết hạn (gọi khi đã giữ lock)."""
    now = _now()
    expired = [k for k, v in _store.items() if v["expires_at"] < now]
    for k in expired:
        del _store[k]


def generate_pkce() -> tuple[str, str]:
    """
    Tạo cặp (code_verifier, code_challenge) theo RFC 7636.
    code_challenge = BASE64URL(SHA256(code_verifier))
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def create_state(nonce: str) -> tuple[str, str, str]:
    """
    Tạo và lưu state mới. Trả về (state, code_verifier, code_challenge).
    """
    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()
    with _lock:
        _prune()
        _store[state] = {
            "nonce": nonce,
            "code_verifier": code_verifier,
            "expires_at": _now() + timedelta(seconds=_STATE_TTL_SECONDS),
        }
    return state, code_verifier, code_challenge


def consume_state(state: str) -> Optional[Dict[str, Any]]:
    """
    Lấy và xóa entry theo state. Trả None nếu không tồn tại hoặc hết hạn.
    Mỗi state chỉ dùng được đúng một lần.
    """
    with _lock:
        entry = _store.pop(state, None)
    if entry is None:
        return None
    if _now() > entry["expires_at"]:
        return None
    return {"nonce": entry["nonce"], "code_verifier": entry["code_verifier"]}
