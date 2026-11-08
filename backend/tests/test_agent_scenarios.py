import os
import tempfile
import unittest

from app.main import (
    chat,
    approve_action,
    reject_action,
    get_audit_logs,
    ChatRequest,
    ChatMessage,
    ApproveRequest,
    RejectRequest,
)
from app.db import init_db, get_connection
from app.tools import email, sheets
from app.tools.registry import registry
from app.confirm.service import confirm_service

class TestAgentScenarios(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "scenario_test.db")
        self.orig_provider = os.environ.get("LLM_PROVIDER")
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["DATABASE_PATH"] = self.db_path
        confirm_service.db_path = self.db_path
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()
        if self.orig_provider is not None:
            os.environ["LLM_PROVIDER"] = self.orig_provider
        else:
            os.environ.pop("LLM_PROVIDER", None)

    def test_scenario_1_search_email_runs_immediately(self):
        """
        Yêu cầu 1: Gõ 'tìm email của Minh' -> tool read chạy ngay, hiện kết quả.
        """
        req = ChatRequest(messages=[ChatMessage(role="user", content="tìm email của Minh")])
        data = chat(req)

        self.assertEqual(data["type"], "tool_executed")
        self.assertEqual(data["tool_name"], "search_email")
        self.assertEqual(data["risk_level"], "read")
        self.assertIsNone(data["pending_action"])

        result = data["result"]
        self.assertIn("emails", result)
        self.assertGreater(result["count"], 0)
        # Kiểm tra email tìm được có chứa 'minh'
        self.assertTrue(any("minh" in m["from"].lower() for m in result["emails"]))

    def test_scenario_2_and_3_send_email_and_approve_or_reject(self):
        """
        Yêu cầu 2: Gõ 'gửi email cho Minh nội dung ...' -> KHÔNG gửi; hiện thẻ xác nhận với To/Tiêu đề/Nội dung.
        Yêu cầu 3: Bấm Duyệt -> mock email được 'gửi' (ghi vào audit_log); bấm Hủy -> không có gì xảy ra.
        """
        initial_sent = len(email.email_provider.sent)

        # Bước A: Gõ lệnh gửi email
        req = ChatRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content="gửi email cho Minh nội dung Đã hoàn thành bản skeleton",
                )
            ]
        )
        data = chat(req)

        # Kiểm tra KHÔNG gửi ngay, mà yêu cầu confirm
        self.assertEqual(data["type"], "confirm_required")
        self.assertEqual(data["tool_name"], "send_email")
        self.assertIsNotNone(data["pending_action"])

        pending = data["pending_action"]
        self.assertEqual(pending["status"], "PENDING")
        self.assertEqual(pending["preview"]["to"], "minh.nguyen@company.com")
        self.assertIn("Đã hoàn thành bản skeleton", pending["preview"]["body"])
        action_id = pending["id"]

        # Kiểm tra email thực tế chưa gửi
        self.assertEqual(len(email.email_provider.sent), initial_sent)

        # Bước B: Thử kịch bản Hủy (reject) với một action khác
        req_reject = ChatRequest(
            messages=[ChatMessage(role="user", content="gửi email cho Minh nội dung Hủy cái này")]
        )
        resp_reject_action = chat(req_reject)
        reject_id = resp_reject_action["pending_action"]["id"]

        reject_resp = reject_action(reject_id, RejectRequest(reason="Không muốn gửi nữa"))
        self.assertTrue(reject_resp["success"])
        self.assertEqual(reject_resp["action"]["status"], "REJECTED")
        self.assertEqual(len(email.email_provider.sent), initial_sent)  # Vẫn không gửi

        # Bước C: Bấm Duyệt cho action đầu tiên
        approve_resp = approve_action(action_id, ApproveRequest())
        self.assertTrue(approve_resp["success"])
        self.assertEqual(approve_resp["action"]["status"], "APPROVED")

        # Mock email đã được "gửi"
        self.assertEqual(len(email.email_provider.sent), initial_sent + 1)
        self.assertEqual(email.email_provider.sent[-1]["to"], "minh.nguyen@company.com")

        # Kiểm tra audit_log có ghi nhận
        audit_resp = get_audit_logs()
        logs = audit_resp["logs"]
        approved_log = [l for l in logs if l.get("action_id") == action_id and l.get("action_type") == "APPROVED"]
        self.assertTrue(len(approved_log) > 0)

    def test_scenario_4_delete_rows_shows_dry_run_preview(self):
        """
        Yêu cầu 4: Gõ 'xóa 10 dòng đầu sheet Doanh thu' -> hiện dry-run (số dòng, ví dụ vài dòng) rồi chờ xác nhận.
        """
        req = ChatRequest(messages=[ChatMessage(role="user", content="xóa 10 dòng đầu sheet Doanh thu")])
        data = chat(req)

        self.assertEqual(data["type"], "confirm_required")
        self.assertEqual(data["tool_name"], "delete_rows")

        pending = data["pending_action"]
        preview = pending["preview"]

        # Kiểm tra thông tin dry-run
        self.assertEqual(preview["sheet_name"], "Doanh thu")
        self.assertEqual(preview["target_count"], 10)
        self.assertIn("Hàng 2 đến Hàng", preview["affected_range"])
        self.assertIn("sample_rows_preview", preview)
        self.assertGreater(len(preview["sample_rows_preview"]), 0)

        # Thử duyệt action xóa dòng
        action_id = pending["id"]
        approve_resp = approve_action(action_id, ApproveRequest())
        self.assertTrue(approve_resp["success"])
        self.assertEqual(approve_resp["action"]["status"], "APPROVED")
        self.assertEqual(approve_resp["action"]["result"]["deleted_count"], 10)

if __name__ == "__main__":
    unittest.main()
