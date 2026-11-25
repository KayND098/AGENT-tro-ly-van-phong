"""
backend/tests/test_auth.py
Bộ kiểm thử xác thực Google OAuth 2.0 (mock 100%, KHÔNG gọi mạng thật).
Tối thiểu 13 test cases theo yêu cầu đề bài.
"""
import hashlib
import os
import secrets
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.db import init_db
from app.auth.db_auth import (
    init_auth_tables,
    upsert_user,
    create_session,
    get_session_user,
    delete_session,
    _hash_token,
)
from app.auth.state_store import create_state, consume_state, _store, _lock
from app.auth.router import require_user, COOKIE_NAME
from app.main import app


def _make_test_client(db_path: str) -> TestClient:
    """Tạo TestClient với dependency override bypass auth cho các route cần login."""
    os.environ["DATABASE_PATH"] = db_path
    os.environ["LLM_PROVIDER"] = "fake"
    os.environ["EMAIL_PROVIDER"] = "mock"
    init_db(db_path)
    init_auth_tables(db_path)
    return TestClient(app, cookies={})


def _fake_user():
    return {"id": 999, "email": "test@example.com", "name": "Test User", "picture": None}


class TestStateStoreAndCallback(unittest.TestCase):
    """Test 1-2: State hết hạn / sai -> từ chối; callback hợp lệ -> tạo user + phiên."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        self.orig_env = {}
        for key in ("DATABASE_PATH", "LLM_PROVIDER", "EMAIL_PROVIDER", "APP_BASE_URL", "ALLOWED_EMAILS"):
            self.orig_env[key] = os.environ.get(key)
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        os.environ.pop("ALLOWED_EMAILS", None)
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()
        for key, val in self.orig_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)
        # Clean up state store
        with _lock:
            _store.clear()

    def test_1_callback_with_wrong_state_is_rejected(self):
        """Callback với state sai -> redirect với error, không tạo phiên."""
        client = TestClient(app)
        resp = client.get("/auth/google/callback?state=INVALID_STATE&code=somecode", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            "error=state_invalid" in resp.headers["location"] or "error=invalid_state" in resp.headers["location"]
        )

    def test_2_callback_with_expired_state_is_rejected(self):
        """State hết hạn (TTL 10 phút) -> từ chối."""
        nonce = secrets.token_urlsafe(16)
        state, cv, cc = create_state(nonce)
        # Force expire
        with _lock:
            _store[state]["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
        # Consume should return None
        result = consume_state(state)
        self.assertIsNone(result)

    def test_3_valid_callback_creates_user_session_cookie(self):
        """
        Callback hợp lệ (mock Google token exchange) -> tạo user, phiên, đặt cookie.
        """
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(nonce)

        # Mock Flow và id_token verification
        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "fake_id_token_string"
        mock_flow_instance.credentials = mock_creds
        mock_flow_instance.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/v2/auth?...", state)

        fake_id_info = {
            "sub": "google_user_123",
            "email": "testuser@gmail.com",
            "name": "Test User",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
            "nonce": nonce,
            "aud": "fake_client_id",
        }

        fake_client_config = {"web": {"client_id": "fake_client_id", "client_secret": "fake_secret"}}

        with patch("app.auth.router.get_web_client_file") as mock_client_file, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info), \
             patch("builtins.open", create=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"fake_client_id","client_secret":"fake_secret"}}'), \
             patch("pathlib.Path.exists", return_value=True):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"fake_client_id","client_secret":"fake_secret"}}'
            mock_client_file.return_value = mock_path

            client = TestClient(app)
            resp = client.get(
                f"/auth/google/callback?state={state}&code=auth_code_123",
                follow_redirects=False,
            )

        self.assertEqual(resp.status_code, 302)
        location = resp.headers.get("location", "")
        self.assertNotIn("error=", location)
        # Kiểm tra fetch_token được gọi đúng với code_verifier đã sinh
        mock_flow_instance.fetch_token.assert_called_once_with(code="auth_code_123", code_verifier=code_verifier)
        # Cookie phải được đặt
        cookies = resp.cookies
        self.assertIn(COOKIE_NAME, resp.headers.get("set-cookie", "").lower().replace("session_id", COOKIE_NAME))


class TestIdTokenValidation(unittest.TestCase):
    """Test 3-4: id_token sai audience hoặc hết hạn -> từ chối."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        self.orig_allowed = os.environ.get("ALLOWED_EMAILS")
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        os.environ.pop("ALLOWED_EMAILS", None)
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()
        if self.orig_allowed is not None:
            os.environ["ALLOWED_EMAILS"] = self.orig_allowed
        else:
            os.environ.pop("ALLOWED_EMAILS", None)
        with _lock:
            _store.clear()

    def test_4_id_token_wrong_audience_rejected(self):
        """id_token sai audience -> verify_oauth2_token ném exception -> callback reject."""
        nonce = secrets.token_urlsafe(16)
        state, cv, cc = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "fake_token"
        mock_flow_instance.credentials = mock_creds

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token has wrong audience")), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"id"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"id"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get(f"/auth/google/callback?state={state}&code=code", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=", resp.headers["location"])

    def test_5_id_token_expired_rejected(self):
        """id_token hết hạn -> verify_oauth2_token ném exception -> callback reject."""
        nonce = secrets.token_urlsafe(16)
        state, cv, cc = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "expired_token"
        mock_flow_instance.credentials = mock_creds

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token expired")), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"id"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"id"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get(f"/auth/google/callback?state={state}&code=code", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=", resp.headers["location"])


class TestAllowedEmails(unittest.TestCase):
    """Test 5: Email không nằm trong ALLOWED_EMAILS -> từ chối."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        os.environ["ALLOWED_EMAILS"] = "allowed@company.com,admin@company.com"
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()
        os.environ.pop("ALLOWED_EMAILS", None)
        with _lock:
            _store.clear()

    def test_6_email_not_in_allowed_list_rejected(self):
        """Email 'outsider@gmail.com' không trong ALLOWED_EMAILS -> redirect error=not_allowed."""
        nonce = secrets.token_urlsafe(16)
        state, cv, cc = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "token"
        mock_flow_instance.credentials = mock_creds

        fake_id_info = {
            "sub": "outsider_sub",
            "email": "outsider@gmail.com",
            "name": "Outsider",
            "nonce": nonce,
        }

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"id"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"id"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get(f"/auth/google/callback?state={state}&code=code", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=email_not_allowed", resp.headers["location"])

    def test_6b_empty_allowed_emails_allows_any_google_user(self):
        """ALLOWED_EMAILS rỗng hoặc không thiết lập -> cho MỌI email được Google chấp nhận."""
        os.environ.pop("ALLOWED_EMAILS", None)
        nonce = secrets.token_urlsafe(16)
        state, cv, cc = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "token"
        mock_flow_instance.credentials = mock_creds

        fake_id_info = {
            "sub": "any_sub_999",
            "email": "anyone@anywhere.org",
            "name": "Anyone",
            "nonce": nonce,
        }

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"id"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"id"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get(f"/auth/google/callback?state={state}&code=code", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("error=", resp.headers.get("location", ""))

    def test_6c_allowed_emails_case_insensitive_and_whitespace(self):
        """ALLOWED_EMAILS không phân biệt hoa thường và bỏ khoảng trắng."""
        os.environ["ALLOWED_EMAILS"] = "  Allowed@Company.COM  "
        nonce = secrets.token_urlsafe(16)
        state, cv, cc = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "token"
        mock_flow_instance.credentials = mock_creds

        fake_id_info = {
            "sub": "sub_case_test",
            "email": "ALLOWED@COMPANY.com",
            "name": "Allowed User",
            "nonce": nonce,
        }

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"id"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"id"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get(f"/auth/google/callback?state={state}&code=code", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("error=", resp.headers.get("location", ""))


class TestSessionCookieExpiry(unittest.TestCase):
    """Test 6: Cookie hết hạn hoặc sai -> /auth/me trả 401."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_7_expired_cookie_returns_401(self):
        """Phiên hết hạn -> /auth/me trả 401."""
        user = upsert_user("sub_exp", "expired@test.com", "Expired User", None, self.db_path)
        token = create_session(user["id"], session_days=30, db_path=self.db_path)
        # Force expire the session
        from app.db import get_db
        id_hash = _hash_token(token)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with get_db(self.db_path) as conn:
            conn.execute("UPDATE sessions SET expires_at = ? WHERE id_hash = ?", (past, id_hash))
            conn.commit()

        client = TestClient(app, cookies={COOKIE_NAME: token})
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_8_wrong_cookie_returns_401(self):
        """Cookie sai -> /auth/me trả 401."""
        client = TestClient(app, cookies={COOKIE_NAME: "completely_wrong_token_value"})
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_9_no_cookie_returns_401(self):
        """Không có cookie -> /auth/me trả 401."""
        client = TestClient(app)
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 401)


class TestLogoutDeletesSession(unittest.TestCase):
    """Test 7: Đăng xuất xóa phiên phía server, cookie cũ không dùng lại."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_10_logout_deletes_session_cookie_invalid_after(self):
        """POST /auth/logout xóa phiên server; cookie cũ không dùng lại được."""
        user = upsert_user("sub_logout", "logout@test.com", "Logout User", None, self.db_path)
        token = create_session(user["id"], session_days=30, db_path=self.db_path)

        # Trước logout — /auth/me trả OK
        client = TestClient(app, cookies={COOKIE_NAME: token})
        resp_before = client.get("/auth/me")
        self.assertEqual(resp_before.status_code, 200)
        self.assertEqual(resp_before.json()["email"], "logout@test.com")

        # Đăng xuất
        resp_logout = client.post(
            "/auth/logout",
            headers={"X-Requested-With": "XMLHttpRequest", "Origin": "http://localhost:5173"},
        )
        self.assertEqual(resp_logout.status_code, 200)

        # Sau logout — cookie cũ không dùng lại được
        client2 = TestClient(app, cookies={COOKIE_NAME: token})
        resp_after = client2.get("/auth/me")
        self.assertEqual(resp_after.status_code, 401)


class TestRouteProtection(unittest.TestCase):
    """Test 8: /chat không cookie -> 401; POST thiếu X-Requested-With -> 403."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_11_chat_without_cookie_returns_401(self):
        """/chat POST không cookie -> 401."""
        client = TestClient(app)
        resp = client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"X-Requested-With": "XMLHttpRequest", "Origin": "http://localhost:5173"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_12_post_without_x_requested_with_returns_403(self):
        """POST /auth/logout thiếu header X-Requested-With -> 403."""
        user = upsert_user("sub_csrf", "csrf@test.com", "CSRF User", None, self.db_path)
        token = create_session(user["id"], session_days=30, db_path=self.db_path)

        client = TestClient(app, cookies={COOKIE_NAME: token})
        # POST logout WITHOUT X-Requested-With
        resp = client.post("/auth/logout")
        self.assertEqual(resp.status_code, 403)

    def test_13_health_is_public(self):
        """/health vẫn công khai, không cần cookie."""
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")


class TestDBOnlyStoresHash(unittest.TestCase):
    """Test bổ sung: DB chỉ lưu băm SHA-256 của cookie, không lưu giá trị gốc."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        os.environ["DATABASE_PATH"] = self.db_path
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_14_db_stores_hash_not_raw_cookie(self):
        """Bảng sessions lưu SHA-256 hash, không lưu giá trị cookie gốc."""
        user = upsert_user("sub_hash", "hash@test.com", "Hash User", None, self.db_path)
        token = create_session(user["id"], session_days=30, db_path=self.db_path)

        expected_hash = hashlib.sha256(token.encode()).hexdigest()

        from app.db import get_db
        with get_db(self.db_path) as conn:
            rows = conn.execute("SELECT id_hash FROM sessions").fetchall()
            stored_hashes = [r["id_hash"] for r in rows]

        # DB phải chứa hash
        self.assertIn(expected_hash, stored_hashes)
        # DB KHÔNG được chứa token gốc
        for h in stored_hashes:
            self.assertNotEqual(h, token)
        # Token gốc phải khác hash
        self.assertNotEqual(token, expected_hash)


class TestPKCEAndErrorHandling(unittest.TestCase):
    """
    Test bộ điều khiển PKCE và các nhánh lỗi chi tiết:
    - fetch_token được gọi với code_verifier đúng bằng giá trị tạo lúc login.
    - state dùng lần hai bị từ chối (state_invalid).
    - state hết hạn bị từ chối (state_expired).
    - log tuyệt đối không chứa authorization code hay token.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auth_test.db")
        self.orig_allowed = os.environ.get("ALLOWED_EMAILS")
        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        os.environ.pop("ALLOWED_EMAILS", None)
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()
        if self.orig_allowed is not None:
            os.environ["ALLOWED_EMAILS"] = self.orig_allowed
        else:
            os.environ.pop("ALLOWED_EMAILS", None)
        with _lock:
            _store.clear()

    def test_15_flow_fetch_token_called_with_exact_code_verifier_from_login(self):
        """flow.fetch_token được gọi với code_verifier đúng bằng giá trị tạo lúc login."""
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "fake_id_token"
        mock_flow_instance.credentials = mock_creds

        fake_id_info = {
            "sub": "sub_pkce_test",
            "email": "pkce@example.com",
            "name": "PKCE User",
            "nonce": nonce,
            "aud": "client_123",
        }

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"client_123"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"client_123"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get(
                f"/auth/google/callback?state={state}&code=secret_auth_code_999",
                follow_redirects=False,
            )

        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("error=", resp.headers.get("location", ""))
        # Xác nhận fetch_token nhận đúng code_verifier tạo từ login
        mock_flow_instance.fetch_token.assert_called_once_with(
            code="secret_auth_code_999",
            code_verifier=code_verifier,
        )

    def test_16_state_used_twice_is_rejected(self):
        """state dùng lần hai bị từ chối (state_invalid)."""
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(nonce)

        mock_flow_instance = MagicMock()
        mock_creds = MagicMock()
        mock_creds.id_token = "fake_token"
        mock_flow_instance.credentials = mock_creds

        fake_id_info = {
            "sub": "sub_double_use",
            "email": "double@example.com",
            "nonce": nonce,
            "aud": "cid",
        }

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow_instance), \
             patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_id_info), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"cid"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"cid"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            # Lần 1: Thành công
            resp1 = client.get(f"/auth/google/callback?state={state}&code=code_1", follow_redirects=False)
            self.assertEqual(resp1.status_code, 302)
            self.assertNotIn("error=", resp1.headers.get("location", ""))

            # Lần 2 với cùng state: Bị từ chối vì state đã bị xóa (dùng 1 lần)
            resp2 = client.get(f"/auth/google/callback?state={state}&code=code_2", follow_redirects=False)
            self.assertEqual(resp2.status_code, 302)
            self.assertIn("error=state_invalid", resp2.headers.get("location", ""))

    def test_17_expired_state_is_rejected(self):
        """state hết hạn (TTL 10 phút) bị từ chối (state_expired)."""
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(nonce)

        # Đặt thời gian hết hạn về quá khứ
        with _lock:
            _store[state]["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)

        client = TestClient(app)
        resp = client.get(f"/auth/google/callback?state={state}&code=code_exp", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=state_expired", resp.headers.get("location", ""))

    def test_18_log_does_not_contain_code_or_token(self):
        """Khi lỗi xảy ra, log chỉ chứa tên loại lỗi, KHÔNG chứa code hoặc token."""
        nonce = secrets.token_urlsafe(16)
        state, code_verifier, code_challenge = create_state(nonce)

        secret_code = "SECRET_AUTH_CODE_XYZ123"
        secret_token = "ya29.SUPER_SECRET_BEARER_TOKEN"

        mock_flow = MagicMock()
        # Giả lập fetch_token ném ngoại lệ chứa thông tin nhạy cảm
        mock_flow.fetch_token.side_effect = RuntimeError(f"Failed with {secret_token}")

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"cid"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"cid"}}'
            mock_cf.return_value = mock_path

            import logging
            with self.assertLogs("app.auth.router", level="WARNING") as log_cm:
                client = TestClient(app)
                resp = client.get(f"/auth/google/callback?state={state}&code={secret_code}", follow_redirects=False)

            self.assertEqual(resp.status_code, 302)
            self.assertIn("error=token_exchange_failed", resp.headers.get("location", ""))

            # Kiểm tra tất cả các dòng log sinh ra không chứa secret_code hay secret_token
            all_logs = " ".join(log_cm.output)
            self.assertNotIn(secret_code, all_logs)
            self.assertNotIn(secret_token, all_logs)
            self.assertIn("token_exchange_failed", all_logs)

    def test_19_login_url_stores_code_verifier_in_state_store(self):
        """GET /auth/google/login khởi tạo Flow và lưu đúng code_verifier sinh ra vào state_store."""
        expected_verifier = "a" * 64
        mock_flow = MagicMock()
        mock_flow.code_verifier = expected_verifier
        mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/v2/auth?state=xyz", "xyz")

        with patch("app.auth.router.get_web_client_file") as mock_cf, \
             patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", return_value=mock_flow), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"web":{"client_id":"cid"}}'):

            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = '{"web":{"client_id":"cid"}}'
            mock_cf.return_value = mock_path

            client = TestClient(app)
            resp = client.get("/auth/google/login", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("accounts.google.com", resp.headers["location"])

        # Kiểm tra trong state store có entry chứa đúng code_verifier này
        with _lock:
            stored_verifiers = [v["code_verifier"] for v in _store.values()]
        self.assertIn(expected_verifier, stored_verifiers)


if __name__ == "__main__":
    unittest.main()
