"""
backend/app/agent/history.py
Quản lý lịch sử hội thoại trong bộ nhớ tách biệt theo từng người dùng (user_id).
- Giới hạn dung lượng: tối đa N tin mỗi người (mặc định 50 tin gần nhất).
- Tự động xóa phiên không hoạt động quá 24 giờ.
- Xóa lịch sử "Cuộc trò chuyện mới" chỉ tác động đến chính người dùng đó.
"""
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

class ConversationHistoryManager:
    def __init__(self, max_messages: int = 50, session_ttl_hours: int = 24):
        self.max_messages = max_messages
        self.session_ttl_hours = session_ttl_hours
        self._store: Dict[Tuple[int, Optional[str]], Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def prune_inactive(self, max_age_hours: Optional[int] = None) -> int:
        """Xóa các phiên không hoạt động quá số giờ chỉ định."""
        ttl = max_age_hours if max_age_hours is not None else self.session_ttl_hours
        cutoff = self._now() - timedelta(hours=ttl)
        removed = 0
        with self._lock:
            expired_keys = [k for k, v in self._store.items() if v["last_activity"] < cutoff]
            for k in expired_keys:
                del self._store[k]
                removed += 1
        return removed

    def get_history(self, user_id: int, conversation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách tin nhắn của người dùng. Tự dọn phiên hết hạn."""
        self.prune_inactive()
        key = (user_id, conversation_id)
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return []
            return list(entry["messages"])

    def add_message(
        self,
        user_id: int,
        message: Dict[str, Any],
        conversation_id: Optional[str] = None,
    ) -> None:
        """Thêm 1 tin nhắn vào lịch sử của người dùng, giữ tối đa max_messages."""
        self.prune_inactive()
        key = (user_id, conversation_id)
        now = self._now()
        with self._lock:
            if key not in self._store:
                self._store[key] = {"last_activity": now, "messages": []}
            entry = self._store[key]
            entry["last_activity"] = now
            entry["messages"].append(message)
            if len(entry["messages"]) > self.max_messages:
                entry["messages"] = entry["messages"][-self.max_messages:]

    def set_history(
        self,
        user_id: int,
        messages: List[Dict[str, Any]],
        conversation_id: Optional[str] = None,
    ) -> None:
        """Cập nhật toàn bộ tin nhắn của người dùng, giữ tối đa max_messages."""
        self.prune_inactive()
        key = (user_id, conversation_id)
        now = self._now()
        trimmed = messages[-self.max_messages:] if len(messages) > self.max_messages else list(messages)
        with self._lock:
            self._store[key] = {
                "last_activity": now,
                "messages": trimmed,
            }

    def clear_history(self, user_id: int, conversation_id: Optional[str] = None) -> None:
        """Chỉ xóa lịch sử của chính user_id (không ảnh hưởng user khác)."""
        with self._lock:
            if conversation_id is not None:
                self._store.pop((user_id, conversation_id), None)
            else:
                keys_to_remove = [k for k in self._store if k[0] == user_id]
                for k in keys_to_remove:
                    del self._store[k]

# Instance singleton mặc định
history_manager = ConversationHistoryManager()
