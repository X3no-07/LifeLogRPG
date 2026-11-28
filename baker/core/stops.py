"""把输入停靠点对应到可播放的路径时间和有依据的地图地物。"""

from math import cos, hypot, radians
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .schema import LogPayload, Stop, Waypoint


Point = Tuple[float, float]
Bounds = Tuple[float, float, float, float]
PlaceMatch = Tuple[str, str, Optional[Sequence[Point]], Optional[Point]]
_CATEGORY = {
    "arts_centre": "艺术中心", "attraction": "景点", "bank": "银行", "bar": "酒吧",
    "books": "书店", "cafe": "咖啡店", "cinema": "影院", "clinic": "诊所",
    "college": "学校", "commercial": "商业建筑", "convenience": "便利店",
    "department_store": "百货商场", "fast_food": "快餐店", "fitness_centre": "健身房", "gallery": "美术馆",
    "hotel": "酒店", "hospital": "医院", "library": "图书馆", "mall": "购物中心",
    "museum": "博物馆", "office": "办公楼", "park": "公园", "pharmacy": "药店",
    "police": "警察局", "post_office": "邮局", "pub": "酒吧", "restaurant": "餐厅",
    "retail": "零售建筑", "school": "学校", "sports_centre": "体育馆", "station": "车站",
    "supermarket": "超市", "theatre": "剧院", "train_station": "火车站",
    "university": "大学", "apartments": "住宅", "house": "住宅",
    "residential": "住宅", "recreation_ground": "活动场地",
    "food": "餐饮", "gov": "政府机构", "medical": "医疗设施",
    "scenic": "景点", "shop": "商店", "transport": "交通设施",
}


def _category(tags: Dict[str, str]) -> str:
    for tag in ("amenity", "shop", "tourism", "leisure", "railway", "office", "building"):
        label = _CATEGORY.get(tags.get(tag, ""))
        if label:
            return label
    if "shop" in tags:
        return _CATEGORY["shop"]
    if "office" in tags:
        return _CATEGORY["office"]
    return ""


def _project(point: Point, bounds: Bounds, size: Tuple[int, int]) -> Point:
    south, west, north, east = bounds
    return ((point[0] - west) / (east - west) * size[0],
            (north - point[1]) / (north - south) * size[1])


def _in_bounds(point: Point, bounds: Bounds) -> bool:
    return bounds[1] <= point[0] <= bounds[3] and bounds[0] <= point[1] <= bounds[2]


def _delta_meters(a: Point, b: Point) -> Point:
    return ((a[0] - b[0]) * 111_320 * cos(radians(b[1])), (a[1] - b[1]) * 111_320)


def _closest(point: Point, start: Point, end: Point) -> Tuple[Point, float]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    u = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq if length_sq else 0
    u = min(1.0, max(0.0, u))
    return (start[0] + dx * u, start[1] + dy * u), u


def _outline_details(point: Point, outline: Sequence[Point]) -> Tuple[bool, float, Point]:
    """找建筑边上最接近地点的点，同时检查地点是否在楼的轮廓内。"""
    inside = False
    closest_point, distance = point, float("inf")
    local = [_delta_meters(vertex, point) for vertex in outline]
    for start, end, a, b in zip(outline, outline[1:], local, local[1:]):
        if (a[1] > 0) != (b[1] > 0) and a[0] - a[1] * (b[0] - a[0]) / (b[1] - a[1]) > 0:
            inside = not inside
        projected, u = _closest((0.0, 0.0), a, b)
        candidate_distance = hypot(*projected)
        if candidate_distance < distance:
            closest_point = (start[0] + (end[0] - start[0]) * u,
                             start[1] + (end[1] - start[1]) * u)
            distance = candidate_distance
    return inside or distance < 0.3, distance, closest_point


def _match_place(point: Point, approach: Point, requested_name: str, payload: LogPayload,
                 osm: Dict[str, List[Dict[str, Any]]], bounds: Bounds) -> PlaceMatch:
    """Use a tagged POI near the input or a building containing it, never a random nearby roof."""
    places = [(place["name"], _category(place.get("tags", {})), place["point"])
              for place in osm.get("places", [])]
    places.extend((p.name, _CATEGORY.get(p.category, ""), (p.lng, p.lat))
                  for p in payload.pois if p.name)
    nearby = [(name, category, position) for name, category, position in places
              if (not requested_name or name == requested_name)
              and _in_bounds(position, bounds)
              and hypot(*_delta_meters(position, point)) <= 12]
    poi = min(nearby, key=lambda p: hypot(*_delta_meters(p[2], point)), default=None)
    target = poi[2] if poi else point
    name = requested_name or (poi[0] if poi else "")
    category = poi[1] if poi else ""
    matching = []
    for building in osm.get("buildings", []):
        outline = building.get("nodes", [])
        if len(outline) < 4 or outline[0] != outline[-1]:
            continue
        # Exclude distant footprints before checking their edges. The margin only
        # allows explicit mapped entrances to match from the nearby sidewalk.
        xs, ys = zip(*outline)
        if not (min(xs) - 0.00015 <= target[0] <= max(xs) + 0.00015
                and min(ys) - 0.00010 <= target[1] <= max(ys) + 0.00010):
            continue
        inside, _, _ = _outline_details(target, outline)
        entrances = [p for p in building.get("entrances", []) if _in_bounds(p, bounds)]
        entrance_close = any(hypot(*_delta_meters(p, target)) <= 9 for p in entrances)
        building_name = building.get("name", "")
        if name and building_name and name != building_name:
            continue
        if inside or entrance_close:
            entrance = min(entrances, key=lambda p: hypot(*_delta_meters(p, approach)), default=None)
            bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            matching.append(((not (name and name == building_name), bool(building.get("part")),
                              not building_name, bbox_area), building, entrance))
    if not matching:
        return name, category, None, None
    _, building, entrance = min(matching, key=lambda candidate: candidate[0])
    name = name or building.get("name", "")
    category = category or _category(building.get("tags", {}))
    return name, category, building["nodes"] if name or category else None, entrance if name or category else None


def _path_time(path: Sequence[Waypoint], point: Point, after: float) -> Tuple[float, float, Point]:
    best_time, best_distance, best_point = 0.0, float("inf"), point
    for start, end in zip(path, path[1:]):
        xy, ratio = _closest(point, (start.x, start.y), (end.x, end.y))
        distance = hypot(xy[0] - point[0], xy[1] - point[1])
        time = start.t + ratio * (end.t - start.t)
        if time > after and distance < best_distance:
            best_time, best_distance, best_point = time, distance, xy
    return best_time, best_distance, best_point


def build_stops(payload: LogPayload, points: Sequence[Point], bounds: Bounds,
                osm: Dict[str, List[Dict[str, Any]]], names: Optional[Sequence[str]] = None, *,
                confirmed_finish: bool = False) -> List[Stop]:
    """输出省略出发点、按播放时间排序的停靠点。"""
    if not payload.path:
        return []
    size = (payload.map.width, payload.map.height)
    path = payload.path
    finish = path[-1]
    stops: List[Stop] = []
    last_time = path[0].t
    south, west, north, east = bounds
    for index, point in enumerate(points[1:], 1):
        is_final = index == len(points) - 1
        if not _in_bounds(point, bounds):
            continue
        projected = _project(point, bounds, size)
        path_point = (projected[0] - 0.5, projected[1] - 0.5)
        if is_final:
            time = finish.t
            distance = hypot(finish.x - path_point[0], finish.y - path_point[1])
            approach_grid = (finish.x, finish.y)
        else:
            time, distance, approach_grid = _path_time(path, path_point, last_time)
        # The walking route may exclude a driving segment from text logs. Avoid
        # assigning a far-away stop to the nearest playable scene.
        if time <= last_time or (distance > 16 and not (confirmed_finish and is_final)):
            continue
        approach = (west + (approach_grid[0] + 0.5) / size[0] * (east - west),
                    north - (approach_grid[1] + 0.5) / size[1] * (north - south))
        name, category, outline, entrance = _match_place(
            point, approach, names[index] if names else "", payload, osm, bounds
        )
        if not is_final and not (name or category):
            continue
        boundary = []
        if outline and all(_in_bounds(vertex, bounds) for vertex in outline):
            boundary = [list(_project(vertex, bounds, size)) for vertex in outline[:-1]]
        marker = projected
        if entrance:
            marker = _project(entrance, bounds, size)
        elif outline:
            _, _, closest_edge = _outline_details(approach, outline)
            if _in_bounds(closest_edge, bounds):
                marker = _project(closest_edge, bounds, size)
        elif not (name or category) and is_final:
            marker = (finish.x + 0.5, finish.y + 0.5)
        stops.append(Stop(
            x=max(0, min(size[0] - 1, marker[0] - 0.5)),
            y=max(0, min(size[1] - 1, marker[1] - 0.5)),
            t=time, name=name, category=category,
            outline=boundary, entrance=entrance is not None,
        ))
        last_time = time
    if not stops or stops[-1].t < finish.t:
        stops.append(Stop(x=finish.x, y=finish.y, t=finish.t))
    return stops
