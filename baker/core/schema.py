"""LogPayload 数据契约

定义 baker 输出的 JSON 结构。Godot 端通过 scripts/loader.gd 严格解析。
任何字段名 / 类型变更必须同步更新本文档与 loader.gd。

JSON schema (顶层):
{
  "meta":       Meta,
  "map":        MapData,
  "path":       [Waypoint, ...],
  "dialogs":    [Dialog, ...],
  "characters": [{"name": str, "color": str}, ...]   # 暂时未使用, 预留
}
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class Meta:
    log_id: str = ""
    title: str = ""
    created_at: str = ""           # ISO 8601 格式, 由 baker 填
    weather: str = "unknown"       # sunny/rainy/cloudy/snowy/unknown
    mood: str = "calm"             # happy/calm/sad/excited/tired
    bgm: str = ""                  # 背景音乐标识 (e.g. "town01.mid")
    # P1.5: 缩放后的时长记录
    original_duration_sec: float = 0.0
    scaled_duration_sec: float = 0.0
    # 原始日志 (debug 用)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MapData:
    tile_size: int = 16            # 每格像素 (P0: 16)
    width: int = 80                # 网格列数
    height: int = 60               # 网格行数
    # grid[y][x] = int 类型码: 0=grass 1=road 2=building 3=water 4=tree
    grid: List[List[int]] = field(default_factory=list)
    legend: Dict[str, str] = field(default_factory=lambda: {
        "0": "grass", "1": "road", "2": "building", "3": "water", "4": "tree",
    })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Waypoint:
    """路径上的一点, 描述角色在 t 时刻应该在 (x, y) 网格坐标处"""
    x: int = 0                     # grid 列
    y: int = 0                     # grid 行
    t: float = 0.0                 # 时刻 (秒), 已缩放
    label: str = ""                # 地点名 / 步骤描述
    transport: str = "walking"     # walking/driving/transit/bicycling

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Dialog:
    """NPC / 主角 对话, 在 t 时刻显示"""
    t: float = 0.0                 # 时刻 (秒), 已缩放
    speaker: str = "Me"            # Me / 老张 / 同事 / 朋友 / 路人 / ...
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Character:
    """预设角色 (P2 阶段用于通讯录)"""
    name: str = "Me"
    color: str = "#f2cc2c"         # hex 颜色
    sprite: str = ""               # 暂未用, 留给 P2.3 捏脸

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LogPayload:
    """完整烘焙输出"""
    meta: Meta = field(default_factory=Meta)
    map: MapData = field(default_factory=MapData)
    path: List[Waypoint] = field(default_factory=list)
    dialogs: List[Dialog] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta.to_dict(),
            "map": self.map.to_dict(),
            "path": [w.to_dict() for w in self.path],
            "dialogs": [d.to_dict() for d in self.dialogs],
            "characters": [c.to_dict() for c in self.characters],
        }
