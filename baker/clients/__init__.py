"""外部 API 客户端

- AmapClient: 高德地图 REST API (geocode / place_text / place_around / route)
- LLMClient: LLM 文本 API (MiniMax / DeepSeek, 配置切换)
- OsmClient: OpenStreetMap Overpass API (路网/建筑/水系/绿化)
"""
from .amap import AmapClient
from .llm import LLMClient
from .osm import OsmClient, parse_overpass, compute_bbox_from_points, expand_bbox

__all__ = [
    "AmapClient", "LLMClient", "OsmClient",
    "parse_overpass", "compute_bbox_from_points", "expand_bbox",
]
