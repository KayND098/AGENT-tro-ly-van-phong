import os
import tempfile
import pytest
import unittest
from datetime import datetime, timezone, timedelta

# Import modules to register tools
from app.db import init_db, get_connection
from app.tools import email, sheets, calendar
from app.tools.registry import registry, RiskLevel
from app.confirm.service import (
    ConfirmService,
    ActionExpiredError,
    ActionAlreadyProcessedError,
    ActionNotFoundError,
    ValidationError,
)

class TestConfirmService(unittest.TestCase):
    def setUp(self):
        # Tạo file database tạm cho mỗi test
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        init_db(self.db_path)
        self.service = ConfirmService(db_path=self.db_path)

        # Lưu lại số lượng email đã gửi trước test
        self.initial_sent_count = len(email.email_provider.sent)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tool_confirm_does_not_execute_before_approval(self):
        """
        Yêu cầu 1: Tool confirm KHÔNG chạy khi chưa được người dùng duyệt.
        - Tạo pending_action với send_email.
        - Trạng thái là PENDING.
        - Provider chưa gửi email nào.
        """
        args = {
            "to": "test.recipient@example.com",
            "subject": "Tiêu đề thử nghiệm",
            "body": "Nội dung email thử nghiệm",
        }

        action = self.service.create_pending_action(
            tool_name="send_email",
            args=args,
            risk_level=RiskLevel.CONFIRM,
        )

        # Kiểm tra action được tạo thành công với status PENDING
        self.assertEqual(action["status"], "PENDING")
        self.assertIsNotNone(action["id"])
        self.assertEqual(action["preview"]["to"], args["to"])

        # Kiểm tra email thực tế CHƯA được gửi trong provider
        self.assertEqual(len(email.email_provider.sent), self.initial_sent_count)

    def test_double_approval_only_executes_once(self):
        """
        Yêu cầu 2: Duyệt 2 lần chỉ chạy 1 lần (Idempotency).
        - Lần 1: Duyệt thành công, tool được thực thi.
        - Lần 2: Bị chặn (báo ActionAlreadyProcessedError), tool KHÔNG bị chạy lần 2.
        """
        args = {
            "to": "minh.nguyen@company.com",
            "subject": "Báo cáo duyệt",
            "body": "Nội dung duyệt",
        }

        action = self.service.create_pending_action(
            tool_name="send_email",
            args=args,
            risk_level=RiskLevel.CONFIRM,
        )
        action_id = action["id"]

        # Duyệt lần 1
        res1 = self.service.approve_action(action_id)
        self.assertEqual(res1["status"], "APPROVED")
        self.assertEqual(len(email.email_provider.sent), self.initial_sent_count + 1)

        # Duyệt lần 2 -> phải bắt lỗi đã xử lý
        with self.assertRaises(ActionAlreadyProcessedError) as ctx:
            self.service.approve_action(action_id)
        self.assertEqual(ctx.exception.status, "APPROVED")

        # Đảm bảo số lượng email gửi đi vẫn chỉ tăng đúng 1 lần
        self.assertEqual(len(email.email_provider.sent), self.initial_sent_count + 1)

    def test_expired_action_cannot_be_approved(self):
        """
        Yêu cầu 3: Quá thời hạn 10 phút thì không chạy được (ActionExpiredError).
        - Tạo pending_action.
        - Giả lập thời gian hết hạn (lùi expires_at về quá khứ).
        - Gọi approve_action -> Ném ngoại lệ ActionExpiredError.
        """
        args = {
            "to": "lan.tran@company.com",
            "subject": "Thư quá hạn",
            "body": "Nội dung quá hạn",
        }

        action = self.service.create_pending_action(
            tool_name="send_email",
            args=args,
            risk_level=RiskLevel.CONFIRM,
        )
        action_id = action["id"]

        # Giả lập thời gian tạo là 15 phút trước (quá hạn 10 phút)
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        past_expires = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_actions SET created_at = ?, expires_at = ? WHERE id = ?",
                (past_time, past_expires, action_id),
            )
            conn.commit()

        # Thử duyệt action đã quá hạn
        with self.assertRaises(ActionExpiredError):
            self.service.approve_action(action_id)

        # Kiểm tra trạng thái trong DB đã chuyển thành EXPIRED
        updated_action = self.service.get_action(action_id)
        self.assertEqual(updated_action["status"], "EXPIRED")

        # Đảm bảo email chưa từng được gửi đi
        self.assertEqual(len(email.email_provider.sent), self.initial_sent_count)

    def test_approve_with_edited_args_replaces_original_and_audits_both(self):
        """
        Yêu cầu 4: Endpoint approve nhận tham số tùy chọn edited_args,
        validate theo schema của tool, dùng nó thay cho args gốc,
        và ghi cả hai vào audit_log.
        """
        original_args = {
            "to": "minh.nguyen@company.com",
            "subject": "Tiêu đề gốc",
            "body": "Nội dung gốc",
        }

        action = self.service.create_pending_action(
            tool_name="send_email",
            args=original_args,
            risk_level=RiskLevel.CONFIRM,
        )
        action_id = action["id"]

        edited_args = {
            "to": "boss@company.com",
            "subject": "Tiêu đề đã được sửa bởi người dùng",
            "body": "Nội dung đã được chỉnh sửa kỹ càng",
        }

        # Duyệt với edited_args
        result = self.service.approve_action(action_id=action_id, edited_args=edited_args)
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(result["executed_args"], edited_args)

        # Kiểm tra email được gửi trong provider chứa tham số đã sửa
        latest_sent = email.email_provider.sent[-1]
        self.assertEqual(latest_sent["to"], "boss@company.com")
        self.assertEqual(latest_sent["subject"], "Tiêu đề đã được sửa bởi người dùng")

        # Kiểm tra audit_log ghi lại cả original_args và edited_args
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_log WHERE action_id = ? AND action_type = 'APPROVED'",
                (action_id,),
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertIn("minh.nguyen@company.com", row["original_args"])
            self.assertIn("boss@company.com", row["edited_args"])

    def test_approve_with_invalid_edited_args_raises_validation_error(self):
        """
        Kiểm tra nếu edited_args thiếu tham số bắt buộc theo schema -> báo ValidationError.
        """
        original_args = {
            "to": "minh.nguyen@company.com",
            "subject": "Tiêu đề gốc",
            "body": "Nội dung gốc",
        }
        action = self.service.create_pending_action(
            tool_name="send_email",
            args=original_args,
        )

        invalid_edited_args = {
            "to": "boss@company.com",
            # Thiếu 'subject' và 'body'
        }

        with self.assertRaises(ValidationError):
            self.service.approve_action(action["id"], edited_args=invalid_edited_args)

if __name__ == "__main__":
    unittest.main()
