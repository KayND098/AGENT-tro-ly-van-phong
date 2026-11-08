import os
import unittest
from unittest.mock import MagicMock, patch

from app.agent.llm import LLMClient, FakeLLM, GeminiLLM, get_llm

class TestGeminiLLM(unittest.TestCase):
    def test_provider_selection_gemini(self):
        """
        Test 1: Chọn đúng provider GeminiLLM theo biến môi trường LLM_PROVIDER=gemini
        khi đã cung cấp GEMINI_API_KEY.
        """
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "test_mock_api_key_12345",
                "GEMINI_MODEL": "gemini-3.8-flash",
            },
            clear=False,
        ):
            with patch("google.genai.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                llm = get_llm()
                self.assertIsInstance(llm, GeminiLLM)
                self.assertEqual(llm.model, "gemini-3.8-flash")
                # Đảm bảo không in hoặc leak key
                self.assertEqual(llm.api_key, "test_mock_api_key_12345")

    def test_fallback_to_fake_llm_when_missing_key(self):
        """
        Test 2: Tự động fallback về FakeLLM khi cấu hình provider=gemini nhưng thiếu key,
        hoặc khi LLM_PROVIDER=fake.
        """
        # Trường hợp A: LLM_PROVIDER='gemini' nhưng GEMINI_API_KEY rỗng
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": ""}, clear=False):
            llm_no_key = get_llm()
            self.assertIsInstance(llm_no_key, FakeLLM)

        # Trường hợp B: LLM_PROVIDER='fake'
        with patch.dict(os.environ, {"LLM_PROVIDER": "fake", "GEMINI_API_KEY": ""}, clear=False):
            llm_fake = get_llm()
            self.assertIsInstance(llm_fake, FakeLLM)

    def test_gemini_llm_api_error_handling(self):
        """
        Test 3: Xử lý ngoại lệ từ Gemini API (quota, timeout, invalid key) mà không crash,
        trả thông báo lỗi thân thiện cho frontend và không để lộ API key.
        """
        mock_client = MagicMock()
        secret_key = "secret_gemini_api_key_xyz999"
        # Giả lập API ném lỗi Quota hoặc Timeout có chứa secret key bên trong exception message
        mock_client.models.generate_content.side_effect = Exception(
            f"429 Resource has been exhausted (quota limit) with key {secret_key}"
        )

        llm = GeminiLLM(
            api_key=secret_key,
            model="gemini-3.8-flash",
            client=mock_client,
        )

        # Gọi generate_response
        res = llm.generate_response(
            messages=[{"role": "user", "content": "xin chào trợ lý"}],
            available_tools=[],
        )

        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("tool_calls"), [])
        content = res.get("content", "")
        # Phải trả về thông báo lỗi thân thiện
        self.assertTrue(len(content) > 0)
        # Tuyệt đối không để lộ API key trong nội dung trả về frontend
        self.assertNotIn(secret_key, content)

        # Kiểm tra thêm khi API trả về bình thường (success path) với mock client
        mock_success_response = MagicMock()
        mock_success_response.text = "Xin chào! Tôi có thể hỗ trợ gì cho bạn trong công việc hôm nay?"
        mock_client.models.generate_content.side_effect = None
        mock_client.models.generate_content.return_value = mock_success_response

        res_ok = llm.generate_response(
            messages=[{"role": "user", "content": "Xin chào"}],
            available_tools=[],
        )
        self.assertEqual(res_ok.get("content"), "Xin chào! Tôi có thể hỗ trợ gì cho bạn trong công việc hôm nay?")
        self.assertEqual(res_ok.get("tool_calls"), [])
