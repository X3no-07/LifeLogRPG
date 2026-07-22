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
    # grid[y][x] = int 类型码: 0=grass 1=road 2=building 3=water 4=tree 5=sidewalk 6=poi 7=plaza
    grid: List[List[int]] = field(default_factory=list)
    # P1.2 建筑层数 (跟 grid 同步, 0=无建筑, N=N 层)
    # building_heights[y][x] = int 层数 (1/2/3/...); 非建筑 cell 永远是 0
    building_heights: List[List[int]] = field(default_factory=list)
    legend: Dict[str, str] = field(default_factory=lambda: {
        "0": "grass", "1": "road", "2": "building", "3": "water", "4": "tree",
    })
    # P0.3 扩展: 5-7 的图例
    legend_extended: Dict[str, str] = field(default_factory=lambda: {
        "5": "sidewalk", "6": "poi", "7": "plaza",
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
class POI:
    """POI 标记 (从高德 place_around 拉, OSM 真实建筑)
    P0.3 阶段: 显示在地图上, 让用户知道"这是中山公园"等
    """
    name: str = ""                 # "中山公园游客服务中心"
    type: str = ""                 # "风景名胜;风景名胜;国家级景点"
    category: str = ""             # 简化分类: 餐饮/购物/景点/生活/其他
    address: str = ""             # "北京市东城区..."
    lng: float = 0.0
    lat: float = 0.0
    grid_x: int = 0               # 投影到 grid 坐标
    grid_y: int = 0
    distance: int = 0             # 离中心点的米数

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TransitMarker:
    """非 walking 段的端点标记 (P0.4 自适应切片用)
    例: 西单 -> 灵境胡同 walking 后, 灵境胡同 -> 西二旗 是 16km 地铁
    -> 切片只覆盖 walking 段 (~0.7km), 地铁两端画 pin 提示
    Godot 端在 grid 边缘或 overlay 上画 pin 标出"这里坐地铁去了西二旗"
    """
    name: str = ""                # 终点 label (e.g. "西二旗")
    transport: str = "transit"    # transit / driving / bicycling
    # 起点 (lng, lat) - 上一段 walking 终点 / 上一个坐标
    start_lng: float = 0.0
    start_lat: float = 0.0
    # 终点 (lng, lat) - 实际到达地
    end_lng: float = 0.0
    end_lat: float = 0.0
    # 投影到 grid (可能裁剪到边缘, 也可能直接绘到 overlay)
    start_grid_x: int = -1
    start_grid_y: int = -1
    end_grid_x: int = -1
    end_grid_y: int = -1
    # 距离 (米) / 时长 (秒) - 给 UI 提示
    distance_m: float = 0.0
    duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InteriorSlot:
    """建筑内室标记 (P1.3)
    OSM way 上有 amenity / shop / office / tourism 标签的建筑, 取中心 cell 当 slot
    Godot 端画 icon + 名字, 用户点击能进入"室内场景" (P3 阶段)
    """
    name: str = ""                # OSM name tag (e.g. "星巴克咖啡")
    category: str = ""            # 简化分类: cafe / restaurant / shop / office / hotel / hospital / bank / school / museum / pharmacy / other
    raw_tag: str = ""             # 原始 OSM tag 值 (e.g. "amenity=cafe")
    lng: float = 0.0
    lat: float = 0.0
    grid_x: int = 0
    grid_y: int = 0
    # 用于 P1.4 QA: 是否有名字 (没名字可能不重要)
    has_name: bool = False

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
    pois: List[POI] = field(default_factory=list)              # P0.3 新增
    transit_markers: List[TransitMarker] = field(default_factory=list)  # P0.4 新增
    interiors: List[InteriorSlot] = field(default_factory=list)  # P1.3 新增

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta.to_dict(),
            "map": self.map.to_dict(),
            "path": [w.to_dict() for w in self.path],
            "dialogs": [d.to_dict() for d in self.dialogs],
            "characters": [c.to_dict() for c in self.characters],
            "pois": [p.to_dict() for p in self.pois],                  # P0.3
            "transit_markers": [m.to_dict() for m in self.transit_markers],  # P0.4
            "interiors": [i.to_dict() for i in self.interiors],       # P1.3
        }
