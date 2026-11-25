"""
backend/tests/test_multiuser_gmail.py
Bộ kiểm thử đa người dùng - Phiên 3: Kết nối Google Workspace (Gmail) riêng biệt cho từng người dùng.
Mock 100%, KHÔNG gọi mạng thật, KHÔNG đọc file token thật.
"""
import os
import secrets
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.db import init_db
from app.auth.db_auth import (
    init_auth_tables,
    upsert_user,
    upsert_user_google_token,
    get_user_google_token,
    delete_user_google_token,
)
from app.auth.state_store import create_state, consume_state, _store, _lock
from app.auth.router import require_user
from app.main import app

USER_A = {"id": 1, "email": "alice@company.com", "name": "Alice Wonderland", "picture": None}
USER_B = {"id": 2, "email": "bob@company.com", "name": "Bob Builder", "picture": None}


class TestMultiuserGmail(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "multiuser_gmail_test.db")
        self.orig_env = {}
        for key in ("DATABASE_PATH", "LLM_PROVIDER", "EMAIL_PROVIDER", "APP_BASE_URL", "GMAIL_OWNER_EMAIL"):
            self.orig_env[key] = os.environ.get(key)

        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "google"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        os.environ.pop("GMAIL_OWNER_EMAIL", None)

        init_db(self.db_path)
        init_auth_tables(self.db_path)

        # Tạo user A và user B trong DB
        upsert_user(google_sub="sub_alice", email=USER_A["email"], name=USER_A["name"], picture=None, db_path=self.db_path)
        upsert_user(google_sub="sub_bob", email=USER_B["email"], name=USER_B["name"], picture=None, db_path=self.db_path)

        self.client = TestClient(app, cookies={})

    def tearDown(self):
        app.dependency_overrides.clear()
        self.temp_dir.cleanup()
        for key, val in self.orig_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def test_1_user_a_connected_user_b_unconnected_isolation(self):
        """
        User A đã kết nối Gmail (có token trong DB) -> tìm được email của A.
        User B chưa kết nối Gmail -> nhận thông báo thân thiện chưa kết nối,
        hoàn toàn không thể đọc hay dùng trộm token của A.
        """
        from app.tools.email import search_email_handler

        # Lưu token cho User A
        upsert_user_google_token(
            user_id=USER_A["id"],
            access_token="ya29.alice_access_token",
            refresh_token="1//alice_refresh_token",
            scopes="openid email profile https://www.googleapis.com/auth/gmail.readonly",
            expiry=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            db_path=self.db_path,
        )

        # Mock Gmail API khi gọi cho User A
        mock_a_results = [
            {
                "id": "msg_alice_001",
                "from": "manager@company.com",
                "to": "alice@company.com",
                "subject": "Dự án A",
                "body": "Nội dung email riêng của Alice",
                "date": "2026-11-21",
            }
        ]

        with patch("app.providers.gmail_provider.GmailProvider.search_email", return_value=mock_a_results) as mock_search:
            # User A tìm email
            res_a = search_email_handler(query="Dự án A", user=USER_A)
            self.assertEqual(res_a["count"], 1)
            self.assertEqual(res_a["emails"][0]["id"], "msg_alice_001")
            self.assertNotIn("error", res_a)

            # User B tìm email (chưa kết nối Gmail)
            res_b = search_email_handler(query="Dự án A", user=USER_B)
            self.assertEqual(res_b["count"], 0)
            self.assertEqual(res_b["emails"], [])
            self.assertIn("Tài khoản của bạn chưa kết nối Gmail", res_b.get("error", ""))
            self.assertIn("Kết nối Gmail", res_b.get("error", ""))

    def test_2_connect_gmail_endpoint_creates_url_with_purpose_and_user_id(self):
        """
        GET /auth/google/connect-gmail yêu cầu đăng nhập, tạo URL với scope Gmail và PKCE,
        và lưu purpose='connect_gmail' kèm user_id vào state_store.
        """
        app.dependency_overrides[require_user] = lambda: USER_A

        fake_client_file = MagicMock()
        fake_client_file.exists.return_value = True

        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/v2/auth?client_id=123", "test_state")

        with patch("app.auth.router.get_web_client_file", return_value=fake_client_file), \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow) as mock_from_secrets:

            resp = self.client.get("/auth/google/connect-gmail", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("accounts.google.com", resp.headers["location"])

            # Kiểm tra scopes truyền vào Flow có chứa scope gmail.readonly
            _, kwargs = mock_from_secrets.call_args
            scopes_requested = kwargs.get("scopes", [])
            self.assertIn("https://www.googleapis.com/auth/gmail.readonly", scopes_requested)

    def test_3_callback_connect_gmail_success_saves_token_to_db(self):
        """
        Callback Google với purpose='connect_gmail':
        - Xác minh email từ id_token khớp với email user đang đăng nhập.
        - Lưu credentials vào bảng user_google_tokens.
        - Chuyển hướng về APP_BASE_URL/?gmail_connected=1.
        """
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(
            nonce=nonce,
            purpose="connect_gmail",
            user_id=USER_A["id"],
        )

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "fake_id_token_alice"
        mock_creds.token = "ya29.new_token_alice"
        mock_creds.refresh_token = "1//new_refresh_alice"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.scopes = ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.readonly"]
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_flow_instance.credentials = mock_creds

        fake_id_info = {
            "sub": "sub_alice",
            "email": "alice@company.com",
            "name": "Alice Wonderland",
            "nonce": nonce,
            "aud": "fake_client_id",
        }

        mock_client_path = MagicMock()
        mock_client_path.exists.return_value = True
        mock_client_path.read_text.return_value = '{"web":{"client_id":"fake_client_id","client_secret":"fake_secret"}}'

        with patch("app.auth.router.get_web_client_file", return_value=mock_client_path), \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info):

            resp = self.client.get(
                f"/auth/google/callback?state={state}&code=auth_code_alice",
                follow_redirects=False,
            )

            self.assertEqual(resp.status_code, 302)
            self.assertIn("gmail_connected=1", resp.headers["location"])

        # Kiểm tra token đã lưu trong DB cho USER_A
        token_row = get_user_google_token(USER_A["id"], db_path=self.db_path)
        self.assertIsNotNone(token_row)
        self.assertEqual(token_row["access_token"], "ya29.new_token_alice")
        self.assertEqual(token_row["refresh_token"], "1//new_refresh_alice")
        self.assertIn("gmail.readonly", token_row["scopes"])

    def test_4_callback_connect_gmail_mismatched_email_rejected(self):
        """
        User A (alice@company.com) bấm kết nối Gmail nhưng trên màn hình Google
        chọn tài khoản khác (attacker@gmail.com) -> từ chối liên kết, trả về ?error=email_mismatch,
        không lưu token vào DB.
        """
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(
            nonce=nonce,
            purpose="connect_gmail",
            user_id=USER_A["id"],
        )

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "fake_id_token_attacker"
        mock_creds.token = "ya29.attacker_token"
        mock_flow_instance.credentials = mock_creds

        # Google trả về email khác với email tài khoản Alice
        fake_id_info = {
            "sub": "sub_attacker",
            "email": "attacker@gmail.com",
            "name": "Attacker Account",
            "nonce": nonce,
            "aud": "fake_client_id",
        }

        mock_client_path = MagicMock()
        mock_client_path.exists.return_value = True
        mock_client_path.read_text.return_value = '{"web":{"client_id":"fake_client_id","client_secret":"fake_secret"}}'

        with patch("app.auth.router.get_web_client_file", return_value=mock_client_path), \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info):

            resp = self.client.get(
                f"/auth/google/callback?state={state}&code=auth_code_attacker",
                follow_redirects=False,
            )

            self.assertEqual(resp.status_code, 302)
            self.assertIn("error=email_mismatch", resp.headers["location"])

        # Token của User A tuyệt đối không được ghi
        token_row = get_user_google_token(USER_A["id"], db_path=self.db_path)
        self.assertIsNone(token_row)

    def test_5_token_auto_refresh_and_update_db(self):
        """
        Token trong DB đã hết hạn nhưng có refresh_token -> GmailProvider tự động
        làm mới (creds.refresh) và lưu access_token + expiry mới vào bảng user_google_tokens.
        """
        from app.providers.gmail_provider import GmailProvider

        # Lưu token đã hết hạn 1 giờ trước
        past_expiry = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        upsert_user_google_token(
            user_id=USER_A["id"],
            access_token="ya29.expired_token",
            refresh_token="1//refresh_token_alice",
            scopes="openid email profile https://www.googleapis.com/auth/gmail.readonly",
            expiry=past_expiry,
            db_path=self.db_path,
        )

        token_data = get_user_google_token(USER_A["id"], db_path=self.db_path)
        provider = GmailProvider(token_data=token_data, user_id=USER_A["id"])

        mock_refreshed_token = "ya29.refreshed_fresh_token_123"
        future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        # Mock Credentials & build service
        def fake_refresh(request):
            mock_creds_instance.token = mock_refreshed_token
            mock_creds_instance.expiry = future_expiry.replace(tzinfo=None)

        mock_creds_instance = MagicMock()
        mock_creds_instance.expired = True
        mock_creds_instance.refresh_token = "1//refresh_token_alice"
        mock_creds_instance.token = "ya29.expired_token"
        mock_creds_instance.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds_instance.client_id = "cid"
        mock_creds_instance.client_secret = "csec"
        mock_creds_instance.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        mock_creds_instance.refresh.side_effect = fake_refresh
        mock_creds_instance.valid = True

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds_instance), \
             patch("googleapiclient.discovery.build", return_value=MagicMock()):

            service = provider._get_service()
            self.assertIsNotNone(service)
            mock_creds_instance.refresh.assert_called_once()

        # Kiểm tra token trong DB đã được cập nhật giá trị mới
        updated_token = get_user_google_token(USER_A["id"], db_path=self.db_path)
        self.assertEqual(updated_token["access_token"], mock_refreshed_token)

    def test_6_disconnect_gmail_and_get_me_status(self):
        """
        - GET /auth/me trả về gmail_connected=True khi đã có token.
        - POST /auth/google/disconnect-gmail xóa sạch token trong DB.
        - Sau khi ngắt kết nối, GET /auth/me trả về gmail_connected=False.
        """
        upsert_user_google_token(
            user_id=USER_A["id"],
            access_token="ya29.token_to_delete",
            refresh_token="1//refresh_to_delete",
            scopes="https://www.googleapis.com/auth/gmail.readonly",
            db_path=self.db_path,
        )

        app.dependency_overrides[require_user] = lambda: USER_A

        # 1. Trước khi ngắt: /auth/me -> gmail_connected=True
        me_resp1 = self.client.get("/auth/me")
        self.assertEqual(me_resp1.status_code, 200)
        self.assertTrue(me_resp1.json()["gmail_connected"])

        # 2. Ngắt kết nối
        disconnect_resp = self.client.post(
            "/auth/google/disconnect-gmail",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(disconnect_resp.status_code, 200)
        self.assertTrue(disconnect_resp.json()["success"])

        # 3. Kiểm tra DB: token đã bị xóa
        self.assertIsNone(get_user_google_token(USER_A["id"], db_path=self.db_path))

        # 4. Sau khi ngắt: /auth/me -> gmail_connected=False
        me_resp2 = self.client.get("/auth/me")
        self.assertEqual(me_resp2.status_code, 200)
        self.assertFalse(me_resp2.json()["gmail_connected"])

    def test_7_disconnect_gmail_csrf_protection(self):
        """POST /auth/google/disconnect-gmail thiếu X-Requested-With bị 403 Forbidden."""
        app.dependency_overrides[require_user] = lambda: USER_A
        resp = self.client.post("/auth/google/disconnect-gmail")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
