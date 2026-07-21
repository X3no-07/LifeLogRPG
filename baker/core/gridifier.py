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
Point = Tuple[float, float]   # (lng, lat)
Grid = List[List[int]]        # grid[y][x] = int cell type
Bounds = Tuple[float, float, float, float]  # (min_lng, min_lat, max_lng, max_lat)


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
                   value: int = 1) -> None:
    """在 grid 上画 Bresenham 直线, 3x3 粗化, 原地修改 grid"""
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
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
    grid: Grid = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
    for i in range(len(waypoints) - 1):
        ax, ay = waypoints[i]["x"], waypoints[i]["y"]
        bx, by = waypoints[i + 1]["x"], waypoints[i + 1]["y"]
        bresenham_line(grid, ax, ay, bx, by, value=1)
    # 点缀 decoration
    rng = random.Random(seed)
    for y in range(grid_h):
        for x in range(grid_w):
            if grid[y][x] != 0:
                continue
            r = rng.random()
            if r < tree_density:
                grid[y][x] = 4
            elif r < tree_density + building_density and 3 < x < grid_w - 3 and 3 < y < grid_h - 3:
                grid[y][x] = 2
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
