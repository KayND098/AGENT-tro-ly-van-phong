"""
backend/tests/test_docker_v1_demo.py
Bộ kiểm thử tự động cho Bản v1 Docker Compose & Chế độ Demo (mock 100%, không gọi mạng).
Bao gồm tối thiểu 6 test cases theo yêu cầu đặc tả:
1. AUTH_MODE thiếu hoặc sai -> hành vi google, không bao giờ demo.
2. AUTH_MODE=demo -> /auth/me trả người dùng demo; cô lập dữ liệu theo user_id vẫn đúng.
3. demo ép EMAIL_PROVIDER=mock dù cấu hình khác; không đọc token.json.
4. demo từ chối khởi động khi APP_BASE_URL là https hoặc tên miền công khai.
5. Ở demo, send_email và delete_rows vẫn bắt buộc đi qua pending_action (không chạy trực tiếp).
6. Đường dẫn dữ liệu đọc từ biến môi trường, không ghi vào thư mục mã nguồn.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, get_db_path
from app.auth.db_auth import init_auth_tables, upsert_user, create_session
from app.auth.config import (
    get_auth_mode,
    is_demo_mode,
    validate_demo_mode_or_raise,
    get_app_base_url,
)
from app.tools.email import get_email_provider, search_email_handler, mock_email_provider
from app.confirm.service import confirm_service
from app.agent.loop import agent_loop
from app.rag.retriever import FtsRetriever


class TestDockerV1Demo(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "demo_test.db")
        self.orig_env = {}
        for key in (
            "AUTH_MODE",
            "DATABASE_PATH",
            "DOCS_DIR",
            "APP_BASE_URL",
            "EMAIL_PROVIDER",
            "LLM_PROVIDER",
            "ALLOWED_EMAILS",
        ):
            self.orig_env[key] = os.environ.get(key)

        os.environ["DATABASE_PATH"] = self.db_path
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["EMAIL_PROVIDER"] = "mock"
        os.environ["APP_BASE_URL"] = "http://localhost:5173"
        init_db(self.db_path)
        init_auth_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()
        for key, val in self.orig_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    # -------------------------------------------------------------------------
    # TEST 1: AUTH_MODE thiếu hoặc sai -> hành vi google, không bao giờ demo
    # -------------------------------------------------------------------------
    def test_1_auth_mode_missing_or_invalid_defaults_to_google(self):
        # Trường hợp biến thiếu
        os.environ.pop("AUTH_MODE", None)
        self.assertEqual(get_auth_mode(), "google")
        self.assertFalse(is_demo_mode())

        # Trường hợp biến mang giá trị lạ / sai
        for invalid_val in ["", "invalid", "1", "true", "DEMO_MODE"]:
            os.environ["AUTH_MODE"] = invalid_val
            self.assertEqual(get_auth_mode(), "google")
            self.assertFalse(is_demo_mode())

        # Khi là google, truy cập /auth/me mà không có cookie phải trả về 401 (không tự cấp demo)
        client = TestClient(app)
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 401)

        # Chỉ khi giá trị chính xác là "demo" (không phân biệt hoa thường)
        os.environ["AUTH_MODE"] = "demo"
        self.assertEqual(get_auth_mode(), "demo")
        self.assertTrue(is_demo_mode())

        os.environ["AUTH_MODE"] = " DEMO "
        self.assertEqual(get_auth_mode(), "demo")
        self.assertTrue(is_demo_mode())

    # -------------------------------------------------------------------------
    # TEST 2: AUTH_MODE=demo -> /auth/me trả người dùng demo; cô lập user_id đúng
    # -------------------------------------------------------------------------
    def test_2_demo_mode_auth_me_returns_demo_user_and_isolation_holds(self):
        os.environ["AUTH_MODE"] = "demo"
        client = TestClient(app)

        # 1. Gọi /auth/me không cần cookie -> tự cấp người dùng Demo và set cookie session
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "Demo")
        self.assertEqual(data["email"], "demo@office-assistant.local")
        self.assertTrue(data.get("demo_mode"))
        self.assertFalse(data.get("gmail_connected"))
        self.assertIn("session_id", resp.cookies)
        demo_user_id = data["id"]

        # 2. Kiểm tra cô lập dữ liệu theo user_id trong chế độ demo
        # Tạo người dùng User B khác trong DB
        user_b = upsert_user(
            google_sub="google_sub_user_b",
            email="user_b@company.com",
            name="User B",
            picture=None,
            db_path=self.db_path,
        )
        user_b_id = user_b["id"]
        self.assertNotEqual(demo_user_id, user_b_id)

        # Tạo pending action thuộc quyền sở hữu của User B
        action_b = confirm_service.create_pending_action(
            tool_name="send_email",
            args={"to": "b@example.com", "subject": "Hi", "body": "Secret"},
            user_id=user_b_id,
        )

        # Demo user gọi GET /actions/pending -> không được thấy thẻ của User B
        resp_pending = client.get("/actions/pending")
        self.assertEqual(resp_pending.status_code, 200)
        action_ids = [a["id"] for a in resp_pending.json().get("actions", [])]
        self.assertNotIn(action_b["id"], action_ids)

        # Demo user cố tình duyệt thẻ của User B -> 404 Not Found
        resp_approve = client.post(
            f"/actions/{action_b['id']}/approve",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp_approve.status_code, 404)

        # Trạng thái thẻ của User B không bị thay đổi
        b_action_check = confirm_service.get_action(action_b["id"], user_id=user_b_id)
        self.assertEqual(b_action_check["status"], "PENDING")

    # -------------------------------------------------------------------------
    # TEST 3: demo ép EMAIL_PROVIDER=mock dù cấu hình khác; không đọc token.json
    # -------------------------------------------------------------------------
    def test_3_demo_mode_forces_mock_email_provider_and_no_token_json_read(self):
        os.environ["AUTH_MODE"] = "demo"
        # Cố tình cấu hình EMAIL_PROVIDER=google
        os.environ["EMAIL_PROVIDER"] = "google"

        # get_email_provider() vẫn bị ép trả về mock_email_provider
        provider = get_email_provider()
        self.assertIs(provider, mock_email_provider)

        # search_email_handler hoạt động qua mock, tuyệt đối không chạm tới token.json
        with patch("pathlib.Path.exists") as mock_exists:
            res = search_email_handler(query="doanh thu", user={"id": 1, "email": "demo@office-assistant.local"})
            self.assertIn("emails", res)
            self.assertGreater(res["count"], 0)
            # Không kiểm tra token.json
            for call in mock_exists.mock_calls:
                self.assertNotIn("token.json", str(call))

        # Endpoint connect-gmail bị từ chối chuyển hướng an toàn về app
        client = TestClient(app)
        resp = client.get("/auth/google/connect-gmail", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=demo_mode_no_gmail", resp.headers.get("location", ""))

    # -------------------------------------------------------------------------
    # TEST 4: demo từ chối khởi động khi APP_BASE_URL là https hoặc tên miền ngoài
    # -------------------------------------------------------------------------
    def test_4_demo_mode_refuses_startup_with_https_or_public_domain(self):
        os.environ["AUTH_MODE"] = "demo"

        # 1. APP_BASE_URL là https -> RuntimeError
        os.environ["APP_BASE_URL"] = "https://localhost:5173"
        with self.assertRaises(RuntimeError) as ctx:
            validate_demo_mode_or_raise()
        self.assertIn("không cho phép sử dụng HTTPS", str(ctx.exception))

        # 2. APP_BASE_URL là tên miền công khai ngoài localhost -> RuntimeError
        os.environ["APP_BASE_URL"] = "http://troly.mycompany.com"
        with self.assertRaises(RuntimeError) as ctx:
            validate_demo_mode_or_raise()
        self.assertIn("chỉ dành cho localhost", str(ctx.exception))

        # 3. APP_BASE_URL là localhost / 127.0.0.1 hợp lệ -> không raise
        for valid_url in ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]:
            os.environ["APP_BASE_URL"] = valid_url
            validate_demo_mode_or_raise()  # phải chạy êm mà không văng exception

    # -------------------------------------------------------------------------
    # TEST 5: Ở demo, send_email và delete_rows vẫn bắt buộc qua pending_action
    # -------------------------------------------------------------------------
    def test_5_demo_mode_send_email_and_delete_rows_require_confirmation(self):
        os.environ["AUTH_MODE"] = "demo"
        os.environ["LLM_PROVIDER"] = "fake"

        demo_user = {"id": 1, "email": "demo@office-assistant.local"}
        sent_before = len(mock_email_provider.sent)

        # Kịch bản 1: Yêu cầu gửi email
        resp_email = agent_loop.run(
            messages=[{"role": "user", "content": "Gửi email cho Lan báo cáo doanh thu"}],
            user=demo_user,
        )
        self.assertEqual(resp_email["type"], "confirm_required")
        self.assertEqual(resp_email["tool_name"], "send_email")
        self.assertIsNotNone(resp_email.get("pending_action"))
        # Email chưa hề được gửi thêm trong mock provider
        self.assertEqual(len(mock_email_provider.sent), sent_before)

        # Kịch bản 2: Yêu cầu xóa dòng sheet
        resp_sheet = agent_loop.run(
            messages=[{"role": "user", "content": "Xóa 3 dòng sheet Khách hàng"}],
            user=demo_user,
        )
        self.assertEqual(resp_sheet["type"], "confirm_required")
        self.assertEqual(resp_sheet["tool_name"], "delete_rows")
        self.assertIsNotNone(resp_sheet.get("pending_action"))

    # -------------------------------------------------------------------------
    # TEST 6: Đường dẫn dữ liệu đọc từ biến môi trường, không ghi vào mã nguồn
    # -------------------------------------------------------------------------
    def test_6_data_paths_read_from_environment_variables(self):
        custom_data_dir = os.path.join(self.temp_dir.name, "custom_volume_data")
        os.makedirs(custom_data_dir, exist_ok=True)
        custom_db_file = os.path.join(custom_data_dir, "custom_app.db")
        custom_docs_dir = os.path.join(custom_data_dir, "docs")
        os.makedirs(custom_docs_dir, exist_ok=True)

        # Tạo file tài liệu mẫu trong thư mục cấu hình mới
        test_doc = Path(custom_docs_dir) / "test_policy.md"
        test_doc.write_text("## Quy chế văn phòng\nNhân viên làm việc linh hoạt từ 8h30.", encoding="utf-8")

        # Cấu hình biến môi trường trỏ sang custom volume
        os.environ["DATABASE_PATH"] = custom_db_file
        os.environ["DOCS_DIR"] = custom_docs_dir

        # Kiểm tra get_db_path()
        self.assertEqual(get_db_path(), custom_db_file)

        # Khởi tạo DB tại vị trí mới
        init_db(custom_db_file)
        self.assertTrue(os.path.exists(custom_db_file))

        # Kiểm tra FtsRetriever tôn trọng DOCS_DIR và DATABASE_PATH
        retriever = FtsRetriever(db_path=custom_db_file, docs_dir=custom_docs_dir)
        self.assertEqual(str(retriever.docs_dir), str(Path(custom_docs_dir).resolve()))
        self.assertEqual(retriever.db_path, custom_db_file)

        results = retriever.retrieve("quy chế văn phòng")
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("Quy chế văn phòng", results[0]["section"])
