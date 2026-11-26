"""道路网格化算法

将高德返回的经纬度 polyline 序列映射到 Godot Tilemap 的网格坐标。
保证:
- 端点投影 (lng,lat) -> (gx, gy) 整数网格
- Bresenham 画线连接端点
- 自动点缀 tree / building 让地图不空
"""
import math
import random
from typing import List, Tuple, Dict, Any

from PIL import Image, ImageDraw

# Type aliases
Point = Tuple[float, float]   # (lng, lat)  (高德坐标系, lng 在前)
Grid = List[List[int]]        # grid[y][x] = int cell type
Bounds = Tuple[float, float, float, float]  # (min_lng, min_lat, max_lng, max_lat)

# Cell types (跟 Godot palette 对齐)
CELL_GRASS = 0
CELL_ROAD = 1
CELL_BUILDING = 2
CELL_WATER = 3
CELL_TREE = 4
CELL_SIDEWALK = 5
CELL_POI = 6  # POI 标记 (4x4 大小)
CELL_PLAZA = 7  # 广场/沙地


def polyline_to_points(polyline: str) -> List[Point]:
    """高德 polyline 字符串 ("lng,lat;lng,lat;...") -> [(lng, lat), ...]"""
    if not polyline:
        return []
    out: List[Point] = []
    for p in polyline.split(";"):
        if "," not in p:
            continue
        try:
            lng, lat = p.split(",")
            out.append((float(lng), float(lat)))
        except ValueError:
            continue
    return out


def points_to_grid(points: List[Point], bounds: Bounds,
                   grid_size: Tuple[int, int]) -> List[Dict[str, int]]:
    """经纬度 -> 网格坐标 (去重连续点)
    bounds: (min_lng, min_lat, max_lng, max_lat)
    grid_size: (w, h) 宽高
    """
    min_lng, min_lat, max_lng, max_lat = bounds
    w, h = grid_size
    if max_lng == min_lng or max_lat == min_lat:
        return []
    waypoints: List[Dict[str, int]] = []
    for lng, lat in points:
        nx = (lng - min_lng) / (max_lng - min_lng)
        # 纬度大=北=grid 顶, 但 grid y=0 是顶, 需要翻转
        ny = 1.0 - (lat - min_lat) / (max_lat - min_lat)
        gx = int(nx * w)
        gy = int(ny * h)
        gx = max(0, min(w - 1, gx))
        gy = max(0, min(h - 1, gy))
        waypoints.append({"x": gx, "y": gy})
    # 去重连续点
    deduped: List[Dict[str, int]] = []
    for p in waypoints:
        if not deduped or deduped[-1] != p:
            deduped.append(p)
    return deduped


def bresenham_line(grid: Grid, x0: int, y0: int, x1: int, y1: int,
                   value: int = 1, thickness: int = 2) -> None:
    """在 grid 上画 Bresenham 直线, 默认 3x3 粗化, 原地修改 grid
    thickness: 1=单线, 2=3x3 粗化 (周围一圈), 3=5x5 粗化
    """
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    # 粗化半径
    rad = thickness - 1
    while True:
        for ox in range(-rad, rad + 1):
            for oy in range(-rad, rad + 1):
                xx, yy = x + ox, y + oy
                if 0 <= xx < w and 0 <= yy < h:
                    grid[yy][xx] = value
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def build_grid_from_waypoints(waypoints: List[Dict[str, int]],
                              grid_w: int, grid_h: int,
                              seed: int = 42,
                              tree_density: float = 0.03,
                              building_density: float = 0.015) -> Grid:
    """根据 waypoints 在 grid 上画路, 撒树和建筑
    - 路上: 1
    - 空地: 0=grass, 4=tree, 2=building (按密度)
    """
    grid: Grid = [[CELL_GRASS for _ in range(grid_w)] for _ in range(grid_h)]
    for i in range(len(waypoints) - 1):
        ax, ay = waypoints[i]["x"], waypoints[i]["y"]
        bx, by = waypoints[i + 1]["x"], waypoints[i + 1]["y"]
        bresenham_line(grid, ax, ay, bx, by, value=CELL_ROAD)
    # 点缀 decoration
    rng = random.Random(seed)
    for y in range(grid_h):
        for x in range(grid_w):
            if grid[y][x] != CELL_GRASS:
                continue
            r = rng.random()
            if r < tree_density:
                grid[y][x] = CELL_TREE
            elif r < tree_density + building_density and 3 < x < grid_w - 3 and 3 < y < grid_h - 3:
                grid[y][x] = CELL_BUILDING
    return grid


def compute_bounds(points: List[Point], pad_ratio: float = 0.05) -> Bounds:
    """根据所有点计算 bounds, 加 padding"""
    if not points:
        return (0.0, 0.0, 0.001, 0.001)
    min_lng = min(p[0] for p in points)
    max_lng = max(p[0] for p in points)
    min_lat = min(p[1] for p in points)
    max_lat = max(p[1] for p in points)
    pad_lng = (max_lng - min_lng) * pad_ratio or 0.001
    pad_lat = (max_lat - min_lat) * pad_ratio or 0.001
    return (min_lng - pad_lng, min_lat - pad_lat, max_lng + pad_lng, max_lat + pad_lat)


def approx_distance_km(a: Point, b: Point) -> float:
    """粗算两点距离 (km) — 1° lat ≈ 111 km, lng 系数 cos(avg_lat) ≈ 0.85 (中纬度)"""
    dlat = abs(b[1] - a[1]) * 111.0
    dlng = abs(b[0] - a[0]) * 111.0 * 0.85
    return (dlat * dlat + dlng * dlng) ** 0.5


# =============================================================================
#  P0.2: OSM 数据网格化
# =============================================================================
# highway 类型 → 道路宽度 (1=小道, 2=主路, 3=高速)
HIGHWAY_WIDTH = {
    "motorway": 3, "motorway_link": 2,
    "trunk": 3, "trunk_link": 2,
    "primary": 2, "primary_link": 2,
    "secondary": 2, "secondary_link": 1,
    "tertiary": 2, "tertiary_link": 1,
    "residential": 1, "unclassified": 1,
    "service": 1, "living_street": 1,
    "footway": 1, "path": 1, "pedestrian": 1, "steps": 1,
}


def osm_to_grid(parsed_osm: Dict[str, List[Dict[str, Any]]],
                bbox: Tuple[float, float, float, float],
                grid_size: Tuple[int, int],
                path_overlay_waypoints: List[Dict[str, int]] = None
                ) -> Tuple[Grid, List[List[int]], Dict[str, Any]]:
    """OSM 数据 → grid (PIL 快栅格化)
    bbox: (min_lat, min_lng, max_lat, max_lng)
    grid_size: (w, h)

    返回: (grid, building_heights, debug_info)
      - grid[y][x] = cell type
      - building_heights[y][x] = 建筑层数 (0=无, 1-20=几层, P1.2)
      - debug_info: {road_count, building_count, water_count, green_count,
                     ground_count, cell_counts}

    栅格化用 PIL (ImageDraw.polygon/line, C 速度): 旧的逐点
    point-in-polygon 是 O(楼数×行×列), 320×240 下要 1 小时;
    PIL 直接填多边形, 同样数据 <1 秒。几何跟旧版一致, 边缘像素
    可能差一格 (参考预览 build_hires.py)。

    绘制顺序 (覆盖优先级, 后面覆盖前面):
      0. 底: parsed 有 ground 数据时默认铺装 (CELL_PLAZA),
         否则草地 (CELL_GRASS, 兼容旧调用)
      1. ground (地面类型: 裸土/停车场/广场/草地; 草最后画, 平局草赢)
      2. green  (公园/森林) - cell 4
      3. water  (河流/湖; 闭合填面, 开放画线宽 2, 不再把整条河填成湖) - cell 3
      4. road (路网; PIL 线, 宽按 highway type; 画在水上, 过河是桥) - cell 1
      5. building (建筑轮廓; 楼后画, 路不再切楼; 层数同步写 heights) - cell 2
      6. path overlay (用户走过的路径) - cell 1
    """
    w, h = grid_size
    base = CELL_PLAZA if "ground" in parsed_osm else CELL_GRASS
    grid_img = Image.new("L", (w, h), base)
    heights_img = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(grid_img)
    hd = ImageDraw.Draw(heights_img)

    # 1) ground (只有 parse_overpass 给了 ground 数据时才有)
    #    画的顺序: dirt, parking, plaza, grass (草最后, 平局草赢)
    ground = parsed_osm.get("ground", [])
    for kind in ("dirt", "parking", "plaza", "grass"):
        val = CELL_GRASS if kind == "grass" else CELL_PLAZA
        for g in ground:
            if g.get("kind") != kind:
                continue
            pts = _project_floats(g["nodes"], bbox, grid_size)
            _pil_poly(dr, pts, val)

    # 2) green
    for g in parsed_osm.get("green", []):
        pts = _project_floats(g["nodes"], bbox, grid_size)
        _pil_poly(dr, pts, CELL_TREE, line_width=1)

    # 3) water: 闭合填面, 开放画线 (宽 2)
    for w_seg in parsed_osm.get("water", []):
        pts = _project_floats(w_seg["nodes"], bbox, grid_size)
        if _is_closed_poly(w_seg["nodes"]):
            _pil_poly(dr, pts, CELL_WATER)
        else:
            _pil_line(dr, pts, CELL_WATER, width=2)

    # 4) road (PIL 线, 宽按 highway type; 全画, 不滤, 路网不断)
    for r in parsed_osm.get("roads", []):
        pts = _project_floats(r["nodes"], bbox, grid_size)
        width = HIGHWAY_WIDTH.get(r["highway_type"], 1)
        _pil_line(dr, pts, CELL_ROAD, width=width)

    # 5) building (楼后画) + heights (层数小的先画, 大的后画, 取 max)
    buildings = parsed_osm.get("buildings", [])
    for b in buildings:
        pts = _project_floats(b["nodes"], bbox, grid_size)
        _pil_poly(dr, pts, CELL_BUILDING, line_width=1)
    for b in sorted(buildings, key=lambda b: b.get("levels", 1)):
        levels = max(1, min(20, int(b.get("levels", 1))))
        pts = _project_floats(b["nodes"], bbox, grid_size)
        _pil_poly(hd, pts, levels, line_width=1)

    # 6) path overlay (用户走过的路径)
    if path_overlay_waypoints:
        pts = [(p["x"], p["y"]) for p in path_overlay_waypoints]
        _pil_line(dr, pts, CELL_ROAD, width=3)

    grid = [[grid_img.getpixel((x, y)) for x in range(w)] for y in range(h)]
    building_heights = [[heights_img.getpixel((x, y)) for x in range(w)] for y in range(h)]

    # debug info
    counts = _count_cells(grid)
    debug_info = {
        "road_count": len(parsed_osm.get("roads", [])),
        "building_count": len(parsed_osm.get("buildings", [])),
        "water_count": len(parsed_osm.get("water", [])),
        "green_count": len(parsed_osm.get("green", [])),
        "ground_count": len(parsed_osm.get("ground", [])),
        "cell_counts": counts,
    }
    return grid, building_heights, debug_info


# ----------------------------------------------------------------------------
#  PIL 快栅格化 helpers (osm_to_grid 用; 旧的 _draw_polygon/_scanline_fill/
#  _stamp_building_heights 留着, 测试直接调它们, 别删)
# ----------------------------------------------------------------------------

def _project_floats(nodes: List[Tuple[float, float]],
                    bbox: Tuple[float, float, float, float],
                    grid_size: Tuple[int, int]) -> List[Tuple[float, float]]:
    """[(lng, lat), ...] WGS84 -> [(fx, fy), ...] 浮点 grid 坐标 (不 clamp,
    PIL 自己裁出界的部分)。bbox: (min_lat, min_lng, max_lat, max_lng)"""
    min_lat, min_lng, max_lat, max_lng = bbox
    gw, gh = grid_size
    if max_lat == min_lat or max_lng == min_lng:
        return [(0.0, 0.0) for _ in nodes]
    out = []
    for lng, lat in nodes:
        fx = (lng - min_lng) / (max_lng - min_lng) * gw
        fy = (1.0 - (lat - min_lat) / (max_lat - min_lat)) * gh
        out.append((fx, fy))
    return out


def _is_closed_poly(nodes: List[Tuple[float, float]]) -> bool:
    """way 是否闭合 (首尾同点)。OSM 闭合 way 会重复首节点 id,
    转成坐标后首尾 float 完全相等。"""
    return len(nodes) >= 3 and nodes[0] == nodes[-1]


def _pil_poly(dr, pts: List[Tuple[float, float]], fill: int,
              line_width: int = 1) -> None:
    """PIL 画多边形: >=3 点填面, 2 点画线, 1 点画点。"""
    if not pts:
        return
    if len(pts) >= 3:
        dr.polygon(pts, fill=fill)
    elif len(pts) == 2:
        dr.line(pts, fill=fill, width=line_width)
    else:
        dr.point(pts[0], fill=fill)


def _pil_line(dr, pts: List[Tuple[float, float]], fill: int, width: int = 1) -> None:
    """PIL 画折线: >=2 点画线, 1 点画点。"""
    if not pts:
        return
    if len(pts) >= 2:
        dr.line(pts, fill=fill, width=max(1, int(width)))
    else:
        dr.point(pts[0], fill=fill)


# ----------------------------------------------------------------------------
#  路线贴路: Amap 稀疏点 -> 沿 OSM 路中心线加密 + 吸附
# ----------------------------------------------------------------------------

def densify_and_snap_route(route_pts_lnglat: List[Tuple[float, float]],
                           osm_roads: List[Dict[str, Any]],
                           bbox: Tuple[float, float, float, float],
                           grid_size: Tuple[int, int],
                           max_gap_cells: float = 2.0,
                           snap_radius_cells: float = 3.0,
                           ) -> List[Dict[str, int]]:
    """Amap 路线点 -> 加密 + 贴到 OSM 路中心线 -> grid waypoints。

    解决两个毛病:
    1. 投影错位: 旧代码用 path 自身 bounds 投影, 跟 grid 的切片 bbox
       对不上, 路会整体偏。改成统一用切片 bbox 投影 (跟 grid 一致)。
    2. 直线横切: Amap 点稀疏, 直线连起来会切进湖、穿过楼。先沿
       Amap 折线加密到每段 <= max_gap_cells, 再把每点吸附到最近的
       OSM 路中心线上 (snap_radius 内), 贴着路的弯曲走。

    route_pts_lnglat: [(lng, lat), ...] WGS84 (Amap polyline 转来的点)
    osm_roads: parsed_osm["roads"] (nodes 为 (lng, lat)); 为空时只加密不吸附
    bbox: 切片 bbox (min_lat, min_lng, max_lat, max_lng), 跟 grid 同系
    返回: [{"x": int, "y": int}, ...] 去重连续点 (跟 points_to_grid 同格式)

    吸附带连续性偏好: 上一点吸附到的那条路, 只要还在半径内就优先用,
    避免在两条平行路之间来回跳。
    """
    w, h = grid_size
    if not route_pts_lnglat:
        return []
    if len(route_pts_lnglat) < 2:
        gx, gy = _lnglat_to_grid_xy(route_pts_lnglat[0][0], route_pts_lnglat[0][1],
                                     bbox, grid_size)
        return [{"x": gx, "y": gy}]

    # 1) 投影到浮点 grid 坐标
    fpts = _project_floats(route_pts_lnglat, bbox, grid_size)

    # 2) 沿折线加密到每段 <= max_gap_cells
    dense: List[Tuple[float, float]] = [fpts[0]]
    for a, b in zip(fpts, fpts[1:]):
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(seg_len / max_gap_cells)))
        for k in range(1, n + 1):
            t = k / n
            dense.append((a[0] + (b[0] - a[0]) * t,
                          a[1] + (b[1] - a[1]) * t))

    # 3) OSM 路段预过滤: 只留路线包围盒附近的段 (扩大 snap_radius)
    road_segs: List[Tuple[float, float, float, float, int]] = []  # ax,ay,bx,by,road_idx
    if osm_roads:
        xs = [p[0] for p in dense]
        ys = [p[1] for p in dense]
        pad = snap_radius_cells + 1.0
        rx0, rx1 = min(xs) - pad, max(xs) + pad
        ry0, ry1 = min(ys) - pad, max(ys) + pad
        for ridx, r in enumerate(osm_roads):
            rpts = _project_floats(r.get("nodes", []), bbox, grid_size)
            for i in range(len(rpts) - 1):
                ax, ay = rpts[i]
                bx, by = rpts[i + 1]
                # 段包围盒跟路线包围盒相交才留
                if max(ax, bx) < rx0 or min(ax, bx) > rx1:
                    continue
                if max(ay, by) < ry0 or min(ay, by) > ry1:
                    continue
                road_segs.append((ax, ay, bx, by, ridx))

    # 4) 吸附
    snapped: List[Tuple[float, float]] = []
    cur_road: int = -1  # 上一点吸附到的路 (连续性偏好)
    for (px, py) in dense:
        best = None  # (dist, cx, cy, road_idx)
        if road_segs:
            # 先试上一点那条路 (在半径内就优先用, 不跳路)
            if cur_road >= 0:
                for (ax, ay, bx, by, ridx) in road_segs:
                    if ridx != cur_road:
                        continue
                    d, cx, cy = _seg_closest(px, py, ax, ay, bx, by)
                    if d <= snap_radius_cells and (best is None or d < best[0]):
                        best = (d, cx, cy, ridx)
            # 再找全局最近
            if best is None:
                for (ax, ay, bx, by, ridx) in road_segs:
                    d, cx, cy = _seg_closest(px, py, ax, ay, bx, by)
                    if d <= snap_radius_cells and (best is None or d < best[0]):
                        best = (d, cx, cy, ridx)
        if best is not None:
            snapped.append((best[1], best[2]))
            cur_road = best[3]
        else:
            snapped.append((px, py))
            cur_road = -1

    # 5) 转整数 grid, clamp, 去重连续点
    out: List[Dict[str, int]] = []
    for (fx, fy) in snapped:
        gx = max(0, min(w - 1, int(fx)))
        gy = max(0, min(h - 1, int(fy)))
        if not out or out[-1] != {"x": gx, "y": gy}:
            out.append({"x": gx, "y": gy})
    return out


def _seg_closest(px: float, py: float, ax: float, ay: float,
                 bx: float, by: float) -> Tuple[float, float, float]:
    """点到线段的最近距离 + 最近点。返回 (dist, cx, cy)。"""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    s2 = vx * vx + vy * vy
    if s2 == 0:
        return math.hypot(wx, wy), ax, ay
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / s2))
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(px - cx, py - cy), cx, cy


def _stamp_building_heights(heights: List[List[int]],
                            nodes: List[Tuple[float, float]],
                            bbox: Tuple[float, float, float, float],
                            grid_size: Tuple[int, int],
                            levels: int) -> None:
    """在建筑覆盖的 cell 上盖 levels (取 max, 避免多层建筑叠加丢失最大层数)"""
    w, h = grid_size
    # 用 _draw_polygon 同款逻辑: 先描边, 再 scanline fill, 标记 cell
    if len(nodes) < 3:
        # 退化成线 (单点)
        for lng, lat in nodes:
            gx, gy = _lnglat_to_grid_xy(lng, lat, bbox, grid_size)
            if 0 <= gx < w and 0 <= gy < h:
                heights[gy][gx] = max(heights[gy][gx], levels)
        return
    # 闭环 building: 起点 = 终点
    if nodes[0] != nodes[-1]:
        nodes = nodes + [nodes[0]]
    # 描边
    for i in range(len(nodes) - 1):
        ax, ay = _lnglat_to_grid_xy(nodes[i][0], nodes[i][1], bbox, grid_size)
        bx, by = _lnglat_to_grid_xy(nodes[i + 1][0], nodes[i + 1][1], bbox, grid_size)
        for px, py in _bresenham_cells(ax, ay, bx, by):
            if 0 <= px < w and 0 <= py < h:
                heights[py][px] = max(heights[py][px], levels)
    # scanline fill
    for y in range(h):
        x_inside: List[int] = []
        for x in range(w):
            # point-in-polygon 简化为: 1px scanline 跟多边形边相交次数
            if _point_in_polygon(x + 0.5, y + 0.5, nodes, bbox, grid_size):
                x_inside.append(x)
        for x in x_inside:
            heights[y][x] = max(heights[y][x], levels)


def _bresenham_cells(x0: int, y0: int, x1: int, y1: int):
    """简化: 跟 gridifier.bresenham_line 一致, 走整数点 (单线, 1 厚度)"""
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return points


def _point_in_polygon(px: float, py: float,
                      poly_nodes_lnglat: List[Tuple[float, float]],
                      bbox: Tuple[float, float, float, float],
                      grid_size: Tuple[int, int]) -> bool:
    """射线法 point-in-polygon (只画 filled building 用)
    poly_nodes_lnglat: [(lng, lat), ...] 闭环
    """
    if len(poly_nodes_lnglat) < 3:
        return False
    w, h = grid_size
    inside = False
    n = len(poly_nodes_lnglat)
    for i in range(n - 1):
        x1, y1 = _lnglat_to_grid_xy(poly_nodes_lnglat[i][0], poly_nodes_lnglat[i][1], bbox, grid_size)
        x2, y2 = _lnglat_to_grid_xy(poly_nodes_lnglat[i + 1][0], poly_nodes_lnglat[i + 1][1], bbox, grid_size)
        # ray casting on (px, py)
        if (y1 > py) != (y2 > py):
            x_intersect = x1 + (py - y1) * (x2 - x1) / (y2 - y1) if y2 != y1 else x1
            if px < x_intersect:
                inside = not inside
    return inside


def _lnglat_to_grid_xy(lng: float, lat: float,
                       bbox: Tuple[float, float, float, float],
                       grid_size: Tuple[int, int]) -> Tuple[int, int]:
    """(lng, lat) WGS84 -> (gx, gy) grid
    bbox: (min_lat, min_lng, max_lat, max_lng)
    """
    min_lat, min_lng, max_lat, max_lng = bbox
    gw, gh = grid_size
    if max_lat == min_lat or max_lng == min_lng:
        return (0, 0)
    nx = (lng - min_lng) / (max_lng - min_lng)
    ny = 1.0 - (lat - min_lat) / (max_lat - min_lat)
    gx = int(nx * gw)
    gy = int(ny * gh)
    gx = max(0, min(gw - 1, gx))
    gy = max(0, min(gh - 1, gy))
    return (gx, gy)


def _draw_polygon(grid: Grid, nodes: List[Tuple[float, float]],
                  bbox: Tuple[float, float, float, float],
                  grid_size: Tuple[int, int],
                  value: int, fill: bool = True,
                  thickness: int = 1) -> None:
    """在 grid 上画多边形 (way)
    nodes: [(lng, lat), ...]  (WGS84)
    算法: 先用 Bresenham 描轮廓 (单线, 确保角点被画), 然后 scanline fill 内部
    thickness: 1=单线轮廓, 2=3x3 粗化
    """
    if not nodes or len(nodes) < 2:
        return
    # 投影
    pts = [_lnglat_to_grid_xy(lng, lat, bbox, grid_size) for (lng, lat) in nodes]
    # 1) 描轮廓 (Bresenham 画线)
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        bresenham_line(grid, a[0], a[1], b[0], b[1], value, thickness=thickness)
    # 2) scanline fill 内部 (fill=True 且至少 3 个顶点)
    if fill and len(pts) >= 3:
        _scanline_fill(grid, pts, value)


def _scanline_fill(grid: Grid, pts: List[Tuple[int, int]], value: int) -> None:
    """多边形扫描线填充 (含水平边 + 角点)"""
    if not pts:
        return
    gh = len(grid)
    gw = len(grid[0]) if gh > 0 else 0
    min_y = max(0, min(p[1] for p in pts))
    max_y = min(gh - 1, max(p[1] for p in pts))
    n = len(pts)
    for y in range(min_y, max_y + 1):
        # 找 y 行的所有交点
        intersections: List[int] = []
        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]
            # 水平边: y == a[1] (== b[1]) 算一个交点 (用 a[0])
            if a[1] == b[1]:
                if y == a[1]:
                    intersections.append(a[0])
                continue
            # 斜边/垂直边: y 在 (min, max] 区间算交点
            if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
                x = a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])
                intersections.append(int(round(x)))
        intersections.sort()
        # 配对填充 (每对交点之间填)
        for k in range(0, len(intersections) - 1, 2):
            x_start = max(0, intersections[k])
            x_end = min(gw - 1, intersections[k + 1])
            for x in range(x_start, x_end + 1):
                grid[y][x] = value


def _draw_polyline_thick(grid: Grid, nodes: List[Tuple[float, float]],
                         bbox: Tuple[float, float, float, float],
                         grid_size: Tuple[int, int],
                         value: int, thickness: int = 1) -> None:
    """画带粗细的折线 (thickness=1 单线, 2 双线, 3 三线)"""
    if not nodes or len(nodes) < 2:
        return
    pts = [_lnglat_to_grid_xy(lng, lat, bbox, grid_size) for (lng, lat) in nodes]
    half = (thickness - 1) / 2
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        # 在每个端点画一个 thickness x thickness 的方块
        for dx in range(-int(half), int(half) + 1):
            for dy in range(-int(half), int(half) + 1):
                if thickness == 1:
                    bresenham_line(grid, ax + dx, ay + dy, bx + dx, by + dy, value)
                else:
                    # 简单粗暴: 在端点放方块 + 用 Bresenham 连
                    _set_cell(grid, ax + dx, ay + dy, value)
                    _set_cell(grid, bx + dx, by + dy, value)
        # 主轴 Bresenham
        bresenham_line(grid, ax, ay, bx, by, value)


def _set_cell(grid: Grid, x: int, y: int, value: int) -> None:
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = value


def _count_cells(grid: Grid) -> Dict[str, int]:
    """统计各 cell type 的数量"""
    counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}
    for row in grid:
        for cell in row:
            counts[cell] = counts.get(cell, 0) + 1
    return counts
