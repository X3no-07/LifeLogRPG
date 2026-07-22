"""P1.4 VLM QA 测试

覆盖:
- vlm_qa._parse_qa_response: 解析 LLM 返回的 JSON (含 markdown/裸 JSON/截断)
- vlm_qa.render_preview: 调 grid_preview 出 PNG
- vlm_qa.run_qa: end-to-end (用 mock requests, 不真调 vision)
"""
import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.vlm_qa import _parse_qa_response, _encode_image, render_preview


class TestParseQAResponse:
    """_parse_qa_response 解析 LLM JSON"""

    def test_direct_json(self):
        content = '{"ok": true, "issues": [], "suggestions": [], "score": 90}'
        result = _parse_qa_response(content)
        assert result["ok"] is True
        assert result["score"] == 90

    def test_markdown_wrapped(self):
        content = '```json\n{"ok": false, "issues": ["x"], "score": 50}\n```'
        result = _parse_qa_response(content)
        assert result["ok"] is False
        assert "x" in result["issues"]

    def test_markdown_no_lang(self):
        content = '```\n{"ok": true, "score": 80}\n```'
        result = _parse_qa_response(content)
        assert result["score"] == 80

    def test_text_then_json(self):
        content = '这是一些解释\n{"ok": true, "score": 70}'
        result = _parse_qa_response(content)
        assert result["score"] == 70

    def test_invalid_returns_fallback(self):
        content = '乱七八槽没 json'
        result = _parse_qa_response(content)
        assert result["ok"] is None
        assert "parse_fail" in result["issues"]

    def test_partial_json(self):
        """找最长 {...}"""
        content = '短 {"a":1} 长 {"ok": true, "score": 88, "issues": [], "suggestions": []}'
        result = _parse_qa_response(content)
        assert result.get("score") == 88


class TestEncodeImage:
    """base64 编码图片"""

    def test_encode_png(self, tmp_path):
        # 写一个最小 PNG
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        url = _encode_image(png)
        assert url.startswith("data:image/png;base64,")
        # 解码验证
        b64 = url.split(",", 1)[1]
        decoded = base64.b64decode(b64)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


class TestRenderPreview:
    """render_preview 调 grid_preview 出 PNG"""

    def test_render_p13(self, tmp_path):
        # 找现有 log
        log_path = Path(__file__).resolve().parent.parent.parent / "saved_logs" / "log_p13.json"
        if not log_path.exists():
            pytest.skip("log_p13.json not generated yet")
        out = tmp_path / "preview.png"
        result = render_preview(log_path, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 100  # 不是空文件


class TestRunQAMocked:
    """run_qa end-to-end (mock vision API)"""

    def test_successful_qa(self, tmp_path):
        from baker.vlm_qa import run_qa
        log_path = Path(__file__).resolve().parent.parent.parent / "saved_logs" / "log_p13.json"
        if not log_path.exists():
            pytest.skip("log_p13.json not generated yet")
        out_dir = tmp_path / "qa"
        # mock requests.post 返回标准成功 response
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": '{"ok": true, "issues": [], "suggestions": ["布局合理"], "score": 88}',
                },
            }],
            "base_resp": {"status_code": 0, "status_msg": ""},
        }
        with patch("baker.vlm_qa.requests.post", return_value=mock_resp) as mock_post:
            result = run_qa(
                log_path, out_dir,
                api_key="sk-test", group_id="12345", base_url="https://api.test.com",
                vision_model="abab6.5s-chat",
            )
        # 应该发了一次请求
        assert mock_post.called
        # result 应该 ok=True score=88
        assert result["ok"] is True
        assert result["score"] == 88
        assert "布局合理" in result["suggestions"]

    def test_qa_with_issues(self, tmp_path):
        from baker.vlm_qa import run_qa
        log_path = Path(__file__).resolve().parent.parent.parent / "saved_logs" / "log_p13.json"
        if not log_path.exists():
            pytest.skip("log_p13.json not generated yet")
        out_dir = tmp_path / "qa"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": '{"ok": false, "issues": ["路网不连通"], "suggestions": [], "score": 40}',
                },
            }],
            "base_resp": {"status_code": 0, "status_msg": ""},
        }
        with patch("baker.vlm_qa.requests.post", return_value=mock_resp):
            result = run_qa(
                log_path, out_dir,
                api_key="sk-test", group_id="12345", base_url="https://api.test.com",
            )
        assert result["ok"] is False
        assert result["score"] == 40
        assert "路网不连通" in result["issues"]

    def test_qa_api_error(self, tmp_path):
        from baker.vlm_qa import run_qa
        log_path = Path(__file__).resolve().parent.parent.parent / "saved_logs" / "log_p13.json"
        if not log_path.exists():
            pytest.skip("log_p13.json not generated yet")
        out_dir = tmp_path / "qa"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"},
        }
        with patch("baker.vlm_qa.requests.post", return_value=mock_resp):
            result = run_qa(
                log_path, out_dir,
                api_key="sk-test", group_id="12345", base_url="https://api.test.com",
            )
        assert result["ok"] is None
        assert "insufficient" in str(result.get("error", ""))

    def test_qa_url_includes_group_id(self, tmp_path):
        from baker.vlm_qa import run_qa
        log_path = Path(__file__).resolve().parent.parent.parent / "saved_logs" / "log_p13.json"
        if not log_path.exists():
            pytest.skip("log_p13.json not generated yet")
        out_dir = tmp_path / "qa"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": '{"ok": true, "score": 80, "issues": [], "suggestions": []}'}}],
            "base_resp": {"status_code": 0},
        }
        with patch("baker.vlm_qa.requests.post", return_value=mock_resp) as mock_post:
            run_qa(
                log_path, out_dir,
                api_key="sk-test", group_id="99999", base_url="https://api.test.com",
            )
        # 验证 URL 包含 groupId
        called_url = mock_post.call_args[0][0]
        assert "groupId=99999" in called_url

    def test_qa_no_group_id_in_url(self, tmp_path):
        """空 group_id 时不应该 append groupId"""
        from baker.vlm_qa import run_qa
        log_path = Path(__file__).resolve().parent.parent.parent / "saved_logs" / "log_p13.json"
        if not log_path.exists():
            pytest.skip("log_p13.json not generated yet")
        out_dir = tmp_path / "qa"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": '{"ok": true, "score": 80, "issues": [], "suggestions": []}'}}],
            "base_resp": {"status_code": 0},
        }
        with patch("baker.vlm_qa.requests.post", return_value=mock_resp) as mock_post:
            run_qa(
                log_path, out_dir,
                api_key="sk-test", group_id="", base_url="https://api.test.com",
            )
        called_url = mock_post.call_args[0][0]
        assert "groupId" not in called_url
