"""MiniMax LLM 客户端

调用 https://api.minimaxi.com/v1/text/chatcompletion_v2
封装 3 个常用场景:
- extract_places(text) -> [str, ...]  提取地点
- generate_meta(text, places) -> dict  生成 weather / mood / dialogs
- chat(messages) -> str                  通用聊天

所有方法在 api_key 为空时返回 None 或 [], 不会抛异常。
LLM 返回非 JSON 时, 用 _parse_json_lenient 兼容 markdown 包裹 / 截断 / CoT 痕迹。
"""
import json
import re
import sys
from typing import Any, Dict, List, Optional


class LLMClient:
    def __init__(self, api_key: str, group_id: str = "",
                 base_url: str = "https://api.minimaxi.com/v1",
                 model: str = "MiniMax-Text-01",
                 timeout: int = 30, verbose: bool = False):
        self.api_key = api_key
        self.group_id = group_id
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.verbose = verbose
        self._requests = None
        if api_key:
            try:
                import requests  # type: ignore
                self._requests = requests
            except ImportError:
                print("[llm] WARN: requests 未安装")

    def enabled(self) -> bool:
        return bool(self.api_key) and self._requests is not None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[llm] {msg}", file=sys.stderr)

    # ------------------------------------------------------------------
    #  公开方法
    # ------------------------------------------------------------------
    def chat(self, prompt: str, max_tokens: int = 500, temperature: float = 0.0) -> Optional[str]:
        """通用 chat, 返回 content 文本 (不解析)"""
        if not self.enabled():
            return None
        url = f"{self.base_url}/text/chatcompletion_v2"
        if self.group_id:
            url += f"?groupId={self.group_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            r = self._requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            data = r.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            self._log(f"chat error: {e}")
        return None

    def extract_places(self, text: str) -> List[str]:
        """从中文生活日志中提取地点列表 (NER)
        改进版 (P0.x):
        - 1-shot example 帮 LLM 理解格式
        - max_tokens 提到 1000 防止 CoT 截断
        - temperature 0 让输出确定
        - 明确"不输出解释"
        """
        if not self.enabled():
            return []
        prompt = (
            "从中文日志提取地点, 输出 JSON 数组, 无其他文字。\n\n"
            "例:\n"
            "日志: 我从天安门走到王府井, 然后坐地铁去国贸\n"
            "输出: [\"天安门\", \"王府井\", \"国贸\"]\n\n"
            "日志: " + text + "\n"
            "输出:"
        )
        content = self.chat(prompt, max_tokens=1000, temperature=0.0)
        if not content:
            return []
        result = _parse_json_lenient(content, expect="array")
        return result if isinstance(result, list) else []

    def generate_meta(self, text: str, places: List[str]) -> Dict[str, Any]:
        """生成 weather / mood / bgm / dialogs"""
        fallback = {"weather": "unknown", "mood": "calm", "bgm": ""}
        if not self.enabled():
            return fallback
        prompt = (
            "你是 GBA 像素 RPG 旁白。根据日志生成场景 meta。\n"
            "严格要求(否则算失败):\n"
            "- 严格只输出 JSON 对象, 第一个字符 {, 最后一个 }\n"
            "- 不要任何解释、分析、markdown 包裹\n\n"
            f"日志: {text}\n"
            f"地点: {', '.join(places)}\n\n"
            "输出 schema:\n"
            '{"weather": "sunny|rainy|cloudy|snowy", '
            '"mood": "happy|calm|sad|excited|tired", '
            '"bgm": "english.id 4-12 字符", '
            '"dialogs": [{"speaker": "Me|老张|同事|朋友|路人", "text": "中文 5-30 字", "t_offset": 0.0-1.0 之间的数字表示对话在路径中的相对时刻"}, ...]}\n'
            "至少 2 条 dialog, 最多 5 条。"
        )
        content = self.chat(prompt, max_tokens=800, temperature=0.7)
        if not content:
            return fallback
        result = _parse_json_lenient(content, expect="object")
        if isinstance(result, dict):
            result.setdefault("weather", "unknown")
            result.setdefault("mood", "calm")
            result.setdefault("bgm", "")
            result.setdefault("dialogs", [])
            return result
        return fallback


# ----------------------------------------------------------------------------
#  JSON 解析容错 (供 baker / 其它客户端复用)
# ----------------------------------------------------------------------------

def _parse_json_lenient(content: str, expect: str = "array") -> Any:
    """宽容解析 LLM 返回的 JSON, 支持 markdown 包裹、前后说明文字、截断等
    expect: "array" 或 "object"
    """
    content = content.strip()
    # 策略 1: 直接 json.loads
    try:
        return json.loads(content)
    except Exception:
        pass
    # 策略 2: 去 markdown 包裹
    cleaned = content
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # 策略 3: 正则找最长的 [...] / {...}
    pattern = r'\[.*?\]' if expect == "array" else r'\{.*?\}'
    candidates = re.findall(pattern, content, re.DOTALL)
    for cand in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None
