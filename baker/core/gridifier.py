"""道路网格化算法

将高德返回的经纬度 polyline 序列映射到 Godot Tilemap 的网格坐标。
保证:
- 端点投影 (lng,lat) -> (gx, gy) 整数网格
- Bresenham 画线连接端点
- 自动点缀 tree / building 让地图不空
"""
import random
from typing import List, Tuple, Dict, Any

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
    """OSM 数据 → grid
    bbox: (min_lat, min_lng, max_lat, max_lng)
    grid_size: (w, h)

    返回: (grid, building_heights, debug_info)
      - grid[y][x] = cell type
      - building_heights[y][x] = 建筑层数 (0=无, 1-20=几层, P1.2)
      - debug_info: {road_count, building_count, water_count, green_count, cell_counts}

    绘制顺序 (覆盖优先级, 后面覆盖前面):
      1. green  (公园/森林) - cell 4
      2. water  (河流/湖)   - cell 3
      3. building (建筑轮廓) - cell 2
      4. road (路网)        - cell 1 (按 highway type 不同宽度)
      5. path overlay (用户走过的路径) - cell 1 (覆盖在 road 上面)
      6. sidewalk (路两边 1 像素人行道) - cell 5
      7. POI (4x4 大块)    - cell 6
    """
    w, h = grid_size
    grid: Grid = [[CELL_GRASS for _ in range(w)] for _ in range(h)]
    # P1.2: 建筑层数 (跟 grid 同步, 默认 0)
    building_heights: List[List[int]] = [[0 for _ in range(w)] for _ in range(h)]

    # 1) green (优先画, 后面会被覆盖)
    for g in parsed_osm.get("green", []):
        _draw_polygon(grid, g["nodes"], bbox, grid_size, CELL_TREE, fill=True)

    # 2) water
    for w_seg in parsed_osm.get("water", []):
        _draw_polygon(grid, w_seg["nodes"], bbox, grid_size, CELL_WATER, fill=True)

    # 3) building (P1.2: 同时写 heights)
    for b in parsed_osm.get("buildings", []):
        levels = b.get("levels", 1)
        _draw_polygon(grid, b["nodes"], bbox, grid_size, CELL_BUILDING, fill=True)
        _stamp_building_heights(building_heights, b["nodes"], bbox, grid_size, levels)

    # 4) road (按 highway_type 宽度)
    for r in parsed_osm.get("roads", []):
        width = HIGHWAY_WIDTH.get(r["highway_type"], 1)
        _draw_polyline_thick(grid, r["nodes"], bbox, grid_size, CELL_ROAD, thickness=width)

    # 5) path overlay (用户走过的路径)
    if path_overlay_waypoints:
        for i in range(len(path_overlay_waypoints) - 1):
            ax, ay = path_overlay_waypoints[i]["x"], path_overlay_waypoints[i]["y"]
            bx, by = path_overlay_waypoints[i + 1]["x"], path_overlay_waypoints[i + 1]["y"]
            bresenham_line(grid, ax, ay, bx, by, CELL_ROAD)

    # 6) sidewalk: road cell 周围 1 像素填 grass→sidewalk (已经画完 road 后)
    # 简化: 不做, 留给 P0.3

    # debug info
    counts = _count_cells(grid)
    debug_info = {
        "road_count": len(parsed_osm.get("roads", [])),
        "building_count": len(parsed_osm.get("buildings", [])),
        "water_count": len(parsed_osm.get("water", [])),
        "green_count": len(parsed_osm.get("green", [])),
        "cell_counts": counts,
    }
    return grid, building_heights, debug_info


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
