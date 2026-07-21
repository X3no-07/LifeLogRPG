"""Baker 输入模式 (Strategy Pattern)

每个 mode 实现一个接口:
  class Mode:
      def run(self) -> LogPayload

支持的 mode:
- MockMode: 用预定义数据, 不需要 Key
- CoordsMode: 用户提供经纬度序列
- TextMode: 用户提供自然语言日志 (LLM 解析 + 高德 API)
"""
from .base import BaseMode
from .mock import MockMode
from .coords import CoordsMode
from .text import TextMode

__all__ = ["BaseMode", "MockMode", "CoordsMode", "TextMode"]
