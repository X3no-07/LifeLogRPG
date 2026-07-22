"""测试 baker/clients/llm.py 的 JSON 解析容错"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.clients.llm import _parse_json_lenient


class TestParseJsonLenient:
    def test_direct_array(self):
        result = _parse_json_lenient('["天安门", "王府井"]')
        assert result == ["天安门", "王府井"]

    def test_direct_object(self):
        result = _parse_json_lenient('{"weather": "sunny"}')
        assert result == {"weather": "sunny"}

    def test_markdown_wrapped(self):
        result = _parse_json_lenient('```json\n["天安门"]\n```')
        assert result == ["天安门"]

    def test_markdown_wrapped_no_lang(self):
        result = _parse_json_lenient('```\n[1, 2, 3]\n```')
        assert result == [1, 2, 3]

    def test_text_then_json(self):
        """LLM 经常先说一段话再给 JSON"""
        result = _parse_json_lenient('这是地点:\n["天安门", "王府井", "国贸"]')
        assert result == ["天安门", "王府井", "国贸"]

    def test_invalid_returns_none(self):
        result = _parse_json_lenient('not json at all')
        assert result is None

    def test_object_in_text(self):
        result = _parse_json_lenient('输出: {"weather": "rainy", "mood": "sad"}', expect="object")
        assert result == {"weather": "rainy", "mood": "sad"}

    def test_malformed_json(self):
        result = _parse_json_lenient('["a", "b",')  # 截断
        assert result is None
