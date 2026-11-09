"""
Bộ kiểm thử GmailProvider & get_email_provider().
Tất cả test đều mock hoàn toàn - KHÔNG gọi mạng thật, KHÔNG đọc file token thật.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


class TestEmailProviderSelection(unittest.TestCase):
    """Test 1: EMAIL_PROVIDER mặc định là mock."""

    def test_default_provider_is_mock(self):
        """Không set EMAIL_PROVIDER -> luôn trả MockEmailProvider."""
        with patch.dict(os.environ, {}, clear=False):
            # Xóa EMAIL_PROVIDER nếu có
            os.environ.pop("EMAIL_PROVIDER", None)
            from app.tools.email import get_email_provider, MockEmailProvider
            provider = get_email_provider()
            self.assertIsInstance(provider, MockEmailProvider)

    def test_explicit_mock_provider(self):
        """EMAIL_PROVIDER=mock -> MockEmailProvider."""
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "mock"}, clear=False):
            from app.tools.email import get_email_provider, MockEmailProvider
            provider = get_email_provider()
            self.assertIsInstance(provider, MockEmailProvider)

    def test_mock_provider_search_returns_expected_format(self):
        """MockEmailProvider.search_email (inbox) trả về format đúng (id, from, to, subject, body, date)."""
        from app.tools.email import MockEmailProvider
        # Dùng instance fresh, chỉ có inbox (không có sent dirty từ test khác)
        provider = MockEmailProvider()
        # Từ khóa chỉ khớp với inbox, không khớp với sent
        results = provider.search_email("báo cáo doanh thu")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        for email in results:
            for field in ["id", "from", "to", "subject", "body", "date"]:
                self.assertIn(field, email, f"Thiếu trường '{field}' trong kết quả mock")

    def test_email_provider_alias_is_mock(self):
        """email_provider (alias ngược tương thích) vẫn là MockEmailProvider."""
        from app.tools.email import email_provider, MockEmailProvider
        self.assertIsInstance(email_provider, MockEmailProvider)


class TestGmailProviderFallback(unittest.TestCase):
    """Test 2: EMAIL_PROVIDER=google nhưng thiếu client_secret.json -> fallback mock, không crash."""

    def test_google_provider_missing_client_secret_fallback_to_mock(self):
        """Thiếu client_secret.json -> cảnh báo thân thiện + trả MockEmailProvider, không raise exception."""
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "google"}, clear=False):
            # Giả lập client_secret_path KHÔNG tồn tại
            with patch(
                "app.providers.gmail_provider.DEFAULT_CLIENT_SECRET_FILE",
                Path("/nonexistent/client_secret.json"),
            ):
                from app.tools.email import get_email_provider, MockEmailProvider
                provider = get_email_provider()
                self.assertIsInstance(provider, MockEmailProvider)

    def test_google_provider_missing_token_fallback_to_mock(self):
        """Có client_secret.json nhưng thiếu token.json -> fallback mock, không crash."""
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "google"}, clear=False):
            fake_secret = MagicMock(spec=Path)
            fake_secret.exists.return_value = True  # client_secret tồn tại
            fake_token = MagicMock(spec=Path)
            fake_token.exists.return_value = False  # token KHÔNG tồn tại

            with patch("app.providers.gmail_provider.DEFAULT_CLIENT_SECRET_FILE", fake_secret), \
                 patch("app.providers.gmail_provider.DEFAULT_TOKEN_FILE", fake_token):
                from app.tools.email import get_email_provider, MockEmailProvider
                provider = get_email_provider()
                self.assertIsInstance(provider, MockEmailProvider)

    def test_google_provider_import_error_fallback_to_mock(self):
        """Nếu import GmailProvider lỗi -> không crash, fallback về mock."""
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "google"}, clear=False):
            with patch.dict("sys.modules", {"app.providers.gmail_provider": None}):
                from app.tools.email import get_email_provider, MockEmailProvider
                try:
                    provider = get_email_provider()
                    self.assertIsInstance(provider, MockEmailProvider)
                except Exception as e:
                    self.fail(f"get_email_provider() không được raise exception, nhưng đã raise: {e}")


class TestGmailAPIError(unittest.TestCase):
    """Test 3: Gmail API lỗi -> thông báo thân thiện, không lộ token."""

    def test_gmail_api_error_returns_friendly_message_no_token_leak(self):
        """
        Khi Gmail API ném exception (network lỗi, quota hết...) -> search_email_handler
        trả response thân thiện kèm 'error' field, không để lộ token hay thông tin nhạy cảm.
        """
        from app.providers.gmail_provider import GmailProvider, sanitize_sensitive_data

        fake_service = MagicMock()
        secret_token = "ya29.a0AfH6SMBxxxxxxSECRET_TOKEN"
        fake_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
            f"HttpError 403: Request had insufficient authentication scopes. Token: {secret_token}"
        )

        gmail_prov = GmailProvider(service=fake_service)

        with self.assertRaises(RuntimeError) as ctx:
            gmail_prov.search_email("test query")

        error_msg = str(ctx.exception)
        # Không được để lộ token thật
        self.assertNotIn(secret_token, error_msg)
        # Phải chứa thông báo lỗi nhưng không chứa token gốc
        self.assertIn("Lỗi", error_msg)

    def test_search_email_handler_api_error_returns_friendly_dict(self):
        """
        search_email_handler bắt lỗi từ provider và trả dict thân thiện (không crash).
        """
        from app.tools import email as email_module

        mock_provider = MagicMock()
        mock_provider.search_email.side_effect = RuntimeError("Mô phỏng lỗi API")

        with patch.object(email_module, "get_email_provider", return_value=mock_provider):
            result = email_module.search_email_handler("test")
            self.assertIsInstance(result, dict)
            self.assertEqual(result["count"], 0)
            self.assertIn("error", result)
            self.assertIsInstance(result["error"], str)
            self.assertGreater(len(result["error"]), 0)
            # Thông báo lỗi phải thân thiện, không lộ token
            self.assertNotIn("ya29.", result["error"])

    def test_sanitize_removes_access_token(self):
        """Hàm sanitize_sensitive_data che token chuẩn ya29.xxx."""
        from app.providers.gmail_provider import sanitize_sensitive_data

        raw = "Error with token ya29.abcdef1234SECRET in request"
        clean = sanitize_sensitive_data(raw)
        self.assertNotIn("ya29.abcdef1234SECRET", clean)
        self.assertIn("[REDACTED_ACCESS_TOKEN]", clean)


class TestGmailSearchResultMapping(unittest.TestCase):
    """Test 4: Kết quả tìm kiếm Gmail được map đúng định dạng mock."""

    def test_gmail_search_result_has_same_format_as_mock(self):
        """
        GmailProvider.search_email trả về list dict có cùng các trường với MockEmailProvider
        (id, from, to, subject, body, date) để frontend hiển thị giống nhau.
        """
        from app.providers.gmail_provider import GmailProvider

        # Giả lập Gmail API trả về 1 message
        fake_service = MagicMock()
        fake_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "msg_gmail_001"}]
        }
        fake_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "id": "msg_gmail_001",
            "snippet": "Đây là đoạn trích ngắn của email thật từ Gmail.",
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@gmail.com"},
                    {"name": "To", "value": "me@gmail.com"},
                    {"name": "Subject", "value": "Tiêu đề email thật"},
                    {"name": "Date", "value": "Mon, 09 Nov 2026 09:00:00 +0700"},
                ]
            },
        }

        provider = GmailProvider(service=fake_service)
        results = provider.search_email("test")

        self.assertEqual(len(results), 1)
        email = results[0]

        # Kiểm tra cùng định dạng với mock
        required_fields = ["id", "from", "to", "subject", "body", "date"]
        for field in required_fields:
            self.assertIn(field, email, f"Thiếu trường '{field}' trong kết quả Gmail")

        self.assertEqual(email["id"], "msg_gmail_001")
        self.assertEqual(email["from"], "sender@gmail.com")
        self.assertEqual(email["to"], "me@gmail.com")
        self.assertEqual(email["subject"], "Tiêu đề email thật")
        self.assertEqual(email["body"], "Đây là đoạn trích ngắn của email thật từ Gmail.")
        self.assertEqual(email["date"], "Mon, 09 Nov 2026 09:00:00 +0700")

    def test_gmail_empty_result_returns_empty_list(self):
        """Gmail API không có thư phù hợp -> trả list rỗng (không crash)."""
        from app.providers.gmail_provider import GmailProvider

        fake_service = MagicMock()
        fake_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": []
        }

        provider = GmailProvider(service=fake_service)
        results = provider.search_email("không có kết quả")
        self.assertEqual(results, [])

    def test_search_email_handler_format_with_mock(self):
        """
        search_email_handler (khi dùng mock) trả đúng format:
        {query, count, emails: [{id, from, to, subject, body, date}, ...]}
        """
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "mock"}, clear=False):
            from app.tools.email import search_email_handler
            result = search_email_handler("minh")
            self.assertIn("query", result)
            self.assertIn("count", result)
            self.assertIn("emails", result)
            self.assertEqual(result["count"], len(result["emails"]))
            self.assertGreater(result["count"], 0)
            for field in ["id", "from", "to", "subject", "body", "date"]:
                self.assertIn(field, result["emails"][0])


if __name__ == "__main__":
    unittest.main()
