"""OSM Overpass API 客户端

OpenStreetMap 开放地理数据, 用于:
- 路网 (highway way)
- 建筑轮廓 (building way)
- 水系 (waterway / natural=water way)
- 绿化 (leisure=park, landuse=grass way)

API: https://overpass-api.de/api/interpreter
- 公共实例, 无需 key
- 限制: 单次 10MB, 推荐 bbox < 1km x 1km
- 坐标系: WGS84 (跟高德 GCJ-02 差 ~50-500m, 中国境内)

WGS84 vs GCJ-02 转换:
- 火星坐标系 (GCJ-02) 是中国加密坐标, OSM 用的是 WGS84
- 偏移 < 1km, 城市内差不多
- 简化方案: 接受 ~500m 误差 (局部切片下不影响), 或用 transform 库
"""
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

# API endpoints
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",  # 主
    "https://overpass.kumi.systems/api/interpreter",  # 备用
    "https://overpass.osm.ch/api/interpreter",  # 备用
]


class OsmClient:
    def __init__(self, timeout: int = 30, verbose: bool = False):
        self.timeout = timeout
        self.verbose = verbose
        self._requests = None
        try:
            import requests  # type: ignore
            self._requests = requests
        except ImportError:
            print("[osm] WARN: requests 未安装, pip install requests")

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[osm] {msg}", file=sys.stderr)

    def enabled(self) -> bool:
        return self._requests is not None

    # ------------------------------------------------------------------
    #  Overpass QL 查询构建
    # ------------------------------------------------------------------
    @staticmethod
    def build_bbox_query(bbox: Tuple[float, float, float, float],
                         timeout: int = 30) -> str:
        """bbox: (min_lat, min_lng, max_lat, max_lng)
        拉路网/建筑/水系/绿化, Overpass QL 语法
        """
        min_lat, min_lng, max_lat, max_lng = bbox
        bbox_str = f"{min_lat},{min_lng},{max_lat},{max_lng}"
        return (
            f"[out:json][timeout:{timeout}];\n"
            f"(\n"
            f"  way[\"highway\"]({bbox_str});\n"
            f"  way[\"building\"]({bbox_str});\n"
            f"  way[\"waterway\"]({bbox_str});\n"
            f"  way[\"natural\"=\"water\"]({bbox_str});\n"
            f"  way[\"leisure\"=\"park\"]({bbox_str});\n"
            f"  way[\"landuse\"=\"grass\"]({bbox_str});\n"
            f"  way[\"landuse\"=\"forest\"]({bbox_str});\n"
            f");\n"
            f"out body;\n"
            f">;\n"
            f"out skel qt;\n"
        )

    # ------------------------------------------------------------------
    #  查询
    # ------------------------------------------------------------------
    def query(self, ql: str) -> Optional[Dict[str, Any]]:
        """发送 Overpass QL, 返回 raw JSON
        自动重试备用 URL
        """
        if not self.enabled():
            return None
        last_err = None
        # User-Agent 必须, 否则 Kumi 镜像 rate-limit
        headers = {"User-Agent": "LifeLogRPG-Baker/0.2 (https://github.com/lifielogrpg)"}
        for url in OVERPASS_URLS:
            try:
                self._log(f"POST {url} (ql len={len(ql)})")
                r = self._requests.post(url, data=ql, headers=headers, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
                self._log(f"  HTTP {r.status_code}: {r.text[:200]}")
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                self._log(f"  error: {e}")
                last_err = str(e)
        print(f"[osm] 全部 URL 失败: {last_err}")
        return None

    def query_bbox(self, bbox: Tuple[float, float, float, float]) -> Optional[Dict[str, Any]]:
        """bbox 范围拉所有相关 way"""
        ql = self.build_bbox_query(bbox)
        return self.query(ql)


# ----------------------------------------------------------------------------
#  OSM 数据解析: raw JSON -> 结构化 way 列表
# ----------------------------------------------------------------------------

def parse_overpass(raw: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """解析 Overpass JSON, 返回分类的 way 列表:
    {
      "roads":    [{highway_type, nodes: [(lat, lng), ...]}, ...],
      "buildings":[{nodes: [(lat, lng), ...], building: 'yes'/'commercial'/..., levels: int,
                    amenity/shop/office/tourism: 室内类别 (P1.3)}, ...],
      "water":    [{nodes: [(lat, lng), ...]}, ...],
      "green":    [{nodes: [(lat, lng), ...], kind: 'park'/'grass'/'forest'}, ...],
    }
    P1.2: building 加 levels 字段 (从 building:levels tag 提, 默认 1)
    P1.3: building 加 interior 字段 (amenity/shop/office/tourism 的简化分类)
    """
    elements = raw.get("elements", [])
    # 1) 收集所有 node (lat, lon) -> 内部统一 (lng, lat) 跟高德 polyline 一致
    nodes_by_id: Dict[str, Tuple[float, float]] = {}
    for el in elements:
        if el.get("type") == "node":
            # 输出 (lng, lat) 顺序
            nodes_by_id[str(el["id"])] = (el["lon"], el["lat"])
    # 2) 解析 way
    roads: List[Dict[str, Any]] = []
    buildings: List[Dict[str, Any]] = []
    water: List[Dict[str, Any]] = []
    green: List[Dict[str, Any]] = []
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        node_ids = el.get("nodes", [])
        # 转换为 (lng, lat) list
        coords: List[Tuple[float, float]] = []
        for nid in node_ids:
            if str(nid) in nodes_by_id:
                coords.append(nodes_by_id[str(nid)])
        if len(coords) < 2:
            continue
        if "highway" in tags:
            roads.append({
                "highway_type": tags.get("highway", "unknown"),
                "name": tags.get("name", ""),
                "nodes": coords,
            })
        elif "building" in tags:
            # P1.2: 提 building:levels, 默认 1
            levels_str = tags.get("building:levels", "1")
            try:
                levels = int(float(levels_str))
            except (ValueError, TypeError):
                levels = 1
            levels = max(1, min(levels, 20))   # clamp [1, 20]
            # P1.3: 提室内类别 (amenity / shop / office / tourism 优先级递减)
            interior = _classify_interior(tags)
            buildings.append({
                "building": tags.get("building", "yes"),
                "name": tags.get("name", ""),
                "levels": levels,
                "interior": interior,   # P1.3: {category, raw_tag} or None
                "nodes": coords,
            })
        elif "waterway" in tags or tags.get("natural") == "water":
            water.append({
                "type": "river" if "waterway" in tags else "lake",
                "name": tags.get("name", ""),
                "nodes": coords,
            })
        elif tags.get("leisure") == "park" or tags.get("landuse") in ("grass", "forest"):
            green.append({
                "kind": tags.get("leisure") or tags.get("landuse", "park"),
                "name": tags.get("name", ""),
                "nodes": coords,
            })
    return {"roads": roads, "buildings": buildings, "water": water, "green": green}


# P1.3: 室内类别映射 (OSM tag value -> 简化 category)
INTERIOR_CATEGORY = {
    # amenity
    "cafe": "cafe", "restaurant": "restaurant", "fast_food": "restaurant",
    "bar": "bar", "pub": "bar",
    "bank": "bank", "atm": "bank",
    "pharmacy": "pharmacy", "hospital": "hospital", "clinic": "hospital", "doctors": "hospital",
    "school": "school", "kindergarten": "school", "college": "school", "university": "school",
    "library": "library",
    "police": "police", "fire_station": "police", "post_office": "post",
    "theatre": "theater", "cinema": "theater",
    # shop (any value)
    # shop: 简化成 "shop" (具体类目太多, MVP 用统一)
    # tourism
    "hotel": "hotel", "guest_house": "hotel", "hostel": "hotel",
    "museum": "museum", "gallery": "museum",
    "attraction": "attraction", "viewpoint": "attraction",
    # leisure
    "fitness_centre": "fitness", "sports_centre": "fitness",
    # office (any value) - 简化
}

# office 和 shop 单独归类 (它们值太多, 简化)
OFFICE_TAGS = {"office", "coworking"}
SHOP_TAGS = {"shop"}  # tag 本身, value 任意


def _classify_interior(tags: Dict[str, str]) -> Optional[Dict[str, str]]:
    """根据 OSM tags 提室内类别
    优先级: amenity > tourism > leisure > shop > office
    返回 {category, raw_tag} or None
    """
    # 1) amenity
    amenity = tags.get("amenity", "")
    if amenity and amenity in INTERIOR_CATEGORY:
        return {"category": INTERIOR_CATEGORY[amenity], "raw_tag": f"amenity={amenity}"}
    # 2) tourism
    tourism = tags.get("tourism", "")
    if tourism and tourism in INTERIOR_CATEGORY:
        return {"category": INTERIOR_CATEGORY[tourism], "raw_tag": f"tourism={tourism}"}
    # 3) leisure
    leisure = tags.get("leisure", "")
    if leisure and leisure in INTERIOR_CATEGORY:
        return {"category": INTERIOR_CATEGORY[leisure], "raw_tag": f"leisure={leisure}"}
    # 4) shop 任意值 -> 统一 "shop"
    if "shop" in tags:
        return {"category": "shop", "raw_tag": f"shop={tags['shop']}"}
    # 5) office 任意值 -> 统一 "office"
    if "office" in tags:
        return {"category": "office", "raw_tag": f"office={tags['office']}"}
    return None


# ----------------------------------------------------------------------------
#  bbox 工具
# ----------------------------------------------------------------------------

def compute_bbox_from_points(points: List[Tuple[float, float]],
                              pad_ratio: float = 0.10) -> Tuple[float, float, float, float]:
    """(lat, lng) 列表 -> bbox (min_lat, min_lng, max_lat, max_lng)
    跟 baker.core.gridifier.compute_bounds 不同, 这个用 (lat, lng) 而非 (lng, lat)
    """
    if not points:
        return (0.0, 0.0, 0.001, 0.001)
    min_lat = min(p[0] for p in points)
    max_lat = max(p[0] for p in points)
    min_lng = min(p[1] for p in points)
    max_lng = max(p[1] for p in points)
    pad_lat = (max_lat - min_lat) * pad_ratio or 0.0005
    pad_lng = (max_lng - min_lng) * pad_ratio or 0.0005
    return (min_lat - pad_lat, min_lng - pad_lng, max_lat + pad_lat, max_lng + pad_lng)


def expand_bbox(bbox: Tuple[float, float, float, float],
                min_size_deg: float = 0.008) -> Tuple[float, float, float, float]:
    """确保 bbox 至少 0.008° 宽 (约 800m), 不够就中心扩展"""
    min_lat, min_lng, max_lat, max_lng = bbox
    h = max_lat - min_lat
    w = max_lng - min_lng
    if h < min_size_deg:
        diff = (min_size_deg - h) / 2
        min_lat -= diff
        max_lat += diff
    if w < min_size_deg:
        diff = (min_size_deg - w) / 2
        min_lng -= diff
        max_lng += diff
    return (min_lat, min_lng, max_lat, max_lng)
