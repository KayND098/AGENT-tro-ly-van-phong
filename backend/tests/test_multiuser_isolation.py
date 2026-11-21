"""
backend/tests/test_multiuser_isolation.py
Bộ kiểm thử Tách biệt dữ liệu Đa người dùng (Phiên 2).
Mock 100%, KHÔNG gọi mạng thật.
Tối thiểu 9 test cases theo yêu cầu đề bài:
1. Người A tạo thẻ; người B không thấy trong /actions/pending.
2. B approve hoặc reject thẻ của A -> 404, thẻ của A không đổi trạng thái.
3. B truy cập /actions/{id} của A -> 404.
4. /audit của A không chứa bản ghi của B và ngược lại.
5. Lịch sử chat của A và B tách biệt; "Cuộc trò chuyện mới" của A không xóa lịch sử của B.
6. Duyệt đúp vẫn chỉ chạy một lần; thẻ hết hạn vẫn bị từ chối (hồi quy).
7. edited_args chỉ chủ sở hữu mới gửi được.
8. Migration chạy trên DB cũ (không có cột user_id) không mất dữ liệu cũ và không crash.
9. search_email với EMAIL_PROVIDER=google và người dùng khác GMAIL_OWNER_EMAIL -> không đọc token.
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.db import init_db, get_connection, record_audit_log
from app.confirm.service import (
    ConfirmService,
    ActionNotFoundError,
    ActionAlreadyProcessedError,
    ActionExpiredError,
    confirm_service,
)
from app.agent.loop import agent_loop, AgentLoop
from app.agent.history import history_manager, ConversationHistoryManager
from app.tools.registry import registry, RiskLevel
from app.tools.email import search_email_handler
from app.auth.router import require_user
from app.main import app


USER_A = {"id": 101, "email": "usera@company.com", "name": "User A", "picture": None}
USER_B = {"id": 202, "email": "userb@company.com", "name": "User B", "picture": None}


class TestMultiuserIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "multiuser_test.db")
        self.orig_env = {}
        for key in ("DATABASE_PATH", "LLM_PROVIDER", "EMAIL_PROVIDER", "GMAIL_OWNER_EMAIL"):
            self.orig_env[key] = os.environ.get(key)

        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ.pop("GMAIL_OWNER_EMAIL", None)

        init_db(self.db_path)
        confirm_service.db_path = self.db_path
        self.service = ConfirmService(db_path=self.db_path)

        # Clear in-memory conversation history
        history_manager.clear_history(user_id=101)
        history_manager.clear_history(user_id=202)

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.temp_dir.cleanup()
        for key, val in self.orig_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def test_1_user_b_cannot_see_user_a_pending_actions(self):
        """1. Người A tạo thẻ; người B không thấy trong /actions/pending."""
        # A tạo pending action
        action_a = self.service.create_pending_action(
            tool_name="send_email",
            args={"to": "minh@company.com", "subject": "Thư A", "body": "Nội dung A"},
            risk_level=RiskLevel.CONFIRM,
            user_id=USER_A["id"],
        )

        # Client đăng nhập với User A
        app.dependency_overrides[require_user] = lambda: USER_A
        resp_a = self.client.get("/actions/pending")
        self.assertEqual(resp_a.status_code, 200)
        action_ids_a = [act["id"] for act in resp_a.json()["actions"]]
        self.assertIn(action_a["id"], action_ids_a)

        # Client đăng nhập với User B
        app.dependency_overrides[require_user] = lambda: USER_B
        resp_b = self.client.get("/actions/pending")
        self.assertEqual(resp_b.status_code, 200)
        action_ids_b = [act["id"] for act in resp_b.json()["actions"]]
        self.assertNotIn(action_a["id"], action_ids_b)

    def test_2_user_b_cannot_approve_or_reject_user_a_action(self):
        """2. B approve hoặc reject thẻ của A -> 404, thẻ của A không đổi trạng thái."""
        action_a = self.service.create_pending_action(
            tool_name="send_email",
            args={"to": "minh@company.com", "subject": "Thư A", "body": "Nội dung A"},
            risk_level=RiskLevel.CONFIRM,
            user_id=USER_A["id"],
        )

        # B cố approve thẻ của A
        app.dependency_overrides[require_user] = lambda: USER_B
        resp_approve = self.client.post(
            f"/actions/{action_a['id']}/approve",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp_approve.status_code, 404)

        # B cố reject thẻ của A
        resp_reject = self.client.post(
            f"/actions/{action_a['id']}/reject",
            json={"reason": "Hủy bởi B"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp_reject.status_code, 404)

        # Trạng thái thẻ của A vẫn là PENDING
        action_check = self.service.get_action(action_a["id"], user_id=USER_A["id"])
        self.assertEqual(action_check["status"], "PENDING")

        # Kiểm tra audit log có ghi nhận UNAUTHORIZED_ACCESS và KHÔNG ghi nội dung thư
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM audit_log WHERE action_type = 'UNAUTHORIZED_ACCESS' AND action_id = ?",
                (action_a["id"],),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["user_id"], USER_B["id"])
            self.assertEqual(row["original_args"], "{}")

    def test_3_user_b_access_user_a_action_returns_404(self):
        """3. B truy cập /actions/{id} của A -> 404 (không dùng 403 để không lộ thẻ)."""
        action_a = self.service.create_pending_action(
            tool_name="send_email",
            args={"to": "lan@company.com", "subject": "Bí mật A", "body": "Nội dung tuyệt mật"},
            risk_level=RiskLevel.CONFIRM,
            user_id=USER_A["id"],
        )

        # B xem chi tiết thẻ của A -> 404
        app.dependency_overrides[require_user] = lambda: USER_B
        resp = self.client.get(f"/actions/{action_a['id']}")
        self.assertEqual(resp.status_code, 404)

        # A xem chi tiết thẻ của chính mình -> 200 OK
        app.dependency_overrides[require_user] = lambda: USER_A
        resp_a = self.client.get(f"/actions/{action_a['id']}")
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.json()["id"], action_a["id"])

    def test_4_audit_logs_isolated_between_users(self):
        """4. /audit của A không chứa bản ghi của B và ngược lại."""
        record_audit_log(
            action_type="EXECUTE_READ",
            tool_name="search_email",
            original_args={"query": "A query"},
            status="SUCCESS",
            user_id=USER_A["id"],
            db_path=self.db_path,
        )
        record_audit_log(
            action_type="EXECUTE_READ",
            tool_name="search_documents",
            original_args={"query": "B query"},
            status="SUCCESS",
            user_id=USER_B["id"],
            db_path=self.db_path,
        )

        # A gọi /audit
        app.dependency_overrides[require_user] = lambda: USER_A
        resp_a = self.client.get("/audit")
        self.assertEqual(resp_a.status_code, 200)
        logs_a = resp_a.json()["logs"]
        self.assertTrue(all(log["user_id"] == USER_A["id"] for log in logs_a))
        self.assertTrue(any(log["tool_name"] == "search_email" for log in logs_a))
        self.assertFalse(any(log["tool_name"] == "search_documents" for log in logs_a))

        # B gọi /audit
        app.dependency_overrides[require_user] = lambda: USER_B
        resp_b = self.client.get("/audit")
        self.assertEqual(resp_b.status_code, 200)
        logs_b = resp_b.json()["logs"]
        self.assertTrue(all(log["user_id"] == USER_B["id"] for log in logs_b))
        self.assertTrue(any(log["tool_name"] == "search_documents" for log in logs_b))
        self.assertFalse(any(log["tool_name"] == "search_email" for log in logs_b))

    def test_5_chat_history_isolated_and_clear_history_only_affects_self(self):
        """5. Lịch sử chat của A và B tách biệt; 'Cuộc trò chuyện mới' của A không xóa lịch sử của B."""
        history_mgr = ConversationHistoryManager(max_messages=10, session_ttl_hours=24)

        # Thêm tin nhắn cho A và B
        history_mgr.add_message(user_id=USER_A["id"], message={"role": "user", "content": "Tin A1"})
        history_mgr.add_message(user_id=USER_A["id"], message={"role": "assistant", "content": "Trả lời A1"})

        history_mgr.add_message(user_id=USER_B["id"], message={"role": "user", "content": "Tin B1"})

        self.assertEqual(len(history_mgr.get_history(user_id=USER_A["id"])), 2)
        self.assertEqual(len(history_mgr.get_history(user_id=USER_B["id"])), 1)

        # A gọi xóa lịch sử
        history_mgr.clear_history(user_id=USER_A["id"])
        self.assertEqual(len(history_mgr.get_history(user_id=USER_A["id"])), 0)
        # Lịch sử B hoàn toàn nguyên vẹn
        self.assertEqual(len(history_mgr.get_history(user_id=USER_B["id"])), 1)
        self.assertEqual(history_mgr.get_history(user_id=USER_B["id"])[0]["content"], "Tin B1")

        # Test qua API endpoint /chat/clear
        app.dependency_overrides[require_user] = lambda: USER_B
        resp = self.client.post("/chat/clear", headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(resp.status_code, 200)

        # Test tự dọn phiên không hoạt động quá 24h
        history_mgr.add_message(user_id=999, message={"role": "user", "content": "Cũ"})
        # Đặt lùi thời gian > 24h
        key = (999, None)
        history_mgr._store[key]["last_activity"] = datetime.now(timezone.utc) - timedelta(hours=25)
        removed = history_mgr.prune_inactive()
        self.assertGreaterEqual(removed, 1)
        self.assertEqual(history_mgr.get_history(user_id=999), [])

    def test_6_double_approval_and_expired_action_regression(self):
        """6. Duyệt đúp vẫn chỉ chạy một lần; thẻ hết hạn vẫn bị từ chối (hồi quy)."""
        action = self.service.create_pending_action(
            tool_name="send_email",
            args={"to": "minh@company.com", "subject": "Hồi quy", "body": "Nội dung"},
            risk_level=RiskLevel.CONFIRM,
            user_id=USER_A["id"],
        )

        app.dependency_overrides[require_user] = lambda: USER_A

        # Lần 1: Duyệt thành công
        resp1 = self.client.post(
            f"/actions/{action['id']}/approve",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json()["action"]["status"], "APPROVED")

        # Lần 2: Duyệt đúp -> 409 Conflict
        resp2 = self.client.post(
            f"/actions/{action['id']}/approve",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp2.status_code, 409)

        # Thẻ hết hạn (> 10 phút)
        action_exp = self.service.create_pending_action(
            tool_name="send_email",
            args={"to": "minh@company.com", "subject": "Hết hạn", "body": "Nội dung"},
            risk_level=RiskLevel.CONFIRM,
            user_id=USER_A["id"],
        )
        # Tua expires_at về quá khứ
        past_iso = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        with get_connection(self.db_path) as conn:
            conn.execute("UPDATE pending_actions SET expires_at = ? WHERE id = ?", (past_iso, action_exp["id"]))
            conn.commit()

        resp_exp = self.client.post(
            f"/actions/{action_exp['id']}/approve",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp_exp.status_code, 400)

    def test_7_edited_args_only_allowed_by_owner(self):
        """7. edited_args chỉ chủ sở hữu mới gửi được."""
        action = self.service.create_pending_action(
            tool_name="send_email",
            args={"to": "minh@company.com", "subject": "Gốc", "body": "Nội dung gốc"},
            risk_level=RiskLevel.CONFIRM,
            user_id=USER_A["id"],
        )

        # User B cố tình gửi edited_args vào thẻ của A
        app.dependency_overrides[require_user] = lambda: USER_B
        resp_b = self.client.post(
            f"/actions/{action['id']}/approve",
            json={"edited_args": {"to": "attacker@evil.com", "subject": "Hacked", "body": "Pwned"}},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp_b.status_code, 404)

        # Thẻ của A vẫn nguyên trạng thái PENDING và không bị ghi đè tham số
        action_curr = self.service.get_action(action["id"], user_id=USER_A["id"])
        self.assertEqual(action_curr["status"], "PENDING")
        self.assertIsNone(action_curr["edited_args"])

        # User A gửi edited_args hợp lệ -> thành công
        app.dependency_overrides[require_user] = lambda: USER_A
        resp_a = self.client.post(
            f"/actions/{action['id']}/approve",
            json={"edited_args": {"to": "minh.nguyen@company.com", "subject": "Đã sửa", "body": "Nội dung mới"}},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.json()["action"]["status"], "APPROVED")
        self.assertEqual(resp_a.json()["action"]["edited_args"]["to"], "minh.nguyen@company.com")

    def test_8_migration_on_legacy_db_without_user_id_column(self):
        """8. Migration chạy trên DB cũ (không có cột user_id) không mất dữ liệu cũ và không crash."""
        legacy_db_path = os.path.join(self.temp_dir.name, "legacy_app.db")
        # Khởi tạo schema cũ không có cột user_id
        conn = sqlite3.connect(legacy_db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE pending_actions (
                id TEXT PRIMARY KEY,
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

            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id TEXT,
                action_type TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                original_args TEXT NOT NULL,
                edited_args TEXT,
                result TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO pending_actions VALUES (
                'legacy_001', 'send_email', '{"to":"old@company.com"}', NULL,
                '{"title":"Preview"}', 'confirm', 'PENDING', NULL,
                '2026-10-01T00:00:00Z', '2026-10-01T00:10:00Z', '2026-10-01T00:00:00Z'
            );

            INSERT INTO audit_log VALUES (
                1, 'legacy_001', 'PENDING_CREATED', 'send_email',
                '{"to":"old@company.com"}', NULL, NULL, 'PENDING', '2026-10-01T00:00:00Z'
            );
        """)
        conn.commit()
        conn.close()

        # Chạy init_db() trên DB cũ để migration chạy tự động
        init_db(legacy_db_path)

        # Kiểm tra bảng đã có cột user_id và dữ liệu cũ còn nguyên
        conn2 = sqlite3.connect(legacy_db_path)
        conn2.row_factory = sqlite3.Row
        row_action = conn2.execute("SELECT * FROM pending_actions WHERE id = 'legacy_001'").fetchone()
        self.assertIsNotNone(row_action)
        self.assertIn("user_id", row_action.keys())
        self.assertIsNone(row_action["user_id"])  # Dữ liệu cũ user_id là NULL

        row_audit = conn2.execute("SELECT * FROM audit_log WHERE id = 1").fetchone()
        self.assertIsNotNone(row_audit)
        self.assertIn("user_id", row_audit.keys())
        self.assertIsNone(row_audit["user_id"])
        conn2.close()

        # Dòng cũ user_id=NULL coi như "không thuộc ai": người dùng thường không thấy
        legacy_service = ConfirmService(db_path=legacy_db_path)
        actions_user_a = legacy_service.list_pending_actions(user_id=USER_A["id"])
        self.assertEqual(len(actions_user_a), 0)

        # Người dùng A truy cập thẻ cũ không thuộc ai -> trả về 404
        with self.assertRaises(ActionNotFoundError):
            legacy_service.get_action("legacy_001", user_id=USER_A["id"])

    def test_9_search_email_guard_with_gmail_owner_email(self):
        """9. search_email với EMAIL_PROVIDER=google và người dùng khác GMAIL_OWNER_EMAIL -> không đọc token."""
        os.environ["EMAIL_PROVIDER"] = "google"
        os.environ["GMAIL_OWNER_EMAIL"] = "boss@company.com"

        # Với tài khoản không phải boss@company.com
        user_employee = {"id": 105, "email": "employee@company.com"}
        with patch("app.providers.gmail_provider.GmailProvider") as mock_gp:
            result = search_email_handler(query="họp", user=user_employee)
            # Không được khởi tạo hoặc đọc GmailProvider
            mock_gp.assert_not_called()
            self.assertEqual(result["count"], 0)
            self.assertIn("Tài khoản này chưa kết nối Gmail", result.get("error", ""))

        # Với tài khoản chính xác là boss@company.com (được phép qua chốt chặn, fallback mock vì chưa có token file thật)
        user_boss = {"id": 1, "email": "boss@company.com"}
        result_boss = search_email_handler(query="họp", user=user_boss)
        self.assertNotIn("Tài khoản này chưa kết nối Gmail", result_boss.get("error", ""))


if __name__ == "__main__":
    unittest.main()
