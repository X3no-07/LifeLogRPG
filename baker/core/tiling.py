"""切片算法: path 范围 -> bbox + 半径

按 master prompt:
> 局部切片加载 (Chunk-based loading): 仅根据日志"起点-路径-终点"构建局部街道切片舞台。
> 结构网格化算法 (Graph Grid Simplification): 将高德地图中现实世界弯曲的道路矢量曲线与复杂经纬度,
>   通过图拓扑简化算法化简归一化为标准的"直角（90°/45°）街道切片",平滑映射至 Godot 4 的 TileMapLayer 像素网格上。

设计:
- 输入: [(lng, lat), ...] 路径点
- 输出: bbox (min_lat, min_lng, max_lat, max_lng) + 中心点
- 半径: 800m 走路 10 分钟范围, 够看到周边

坐标系统:
- OSM 用 WGS84 (lat, lng)
- 高德用 GCJ-02 (lat, lng, 加密, 中国境内偏移 50-500m)
- 简化方案: 局部切片接受 ~500m 误差 (二者差异在城市内)
"""
import math
from typing import List, Tuple

PointLL = Tuple[float, float]  # (lng, lat)
Bbox = Tuple[float, float, float, float]  # (min_lat, min_lng, max_lat, max_lng)


# 地球参数
EARTH_R = 6371000.0  # 半径 米


def meters_per_degree(lat: float) -> Tuple[float, float]:
    """1° 在 (lat, lng) 方向对应多少米
    1° lat ≈ 111.32 km (常值)
    1° lng ≈ 111.32 km * cos(lat) (随纬度变化)
    """
    m_per_lat = math.pi * EARTH_R / 180.0
    m_per_lng = math.pi * EARTH_R * math.cos(math.radians(lat)) / 180.0
    return m_per_lat, m_per_lng


def slice_around_path(path: List[PointLL], radius_m: float = 800.0,
                       pad_ratio: float = 0.10) -> dict:
    """输入路径点 (lng, lat) 列表, 输出切片
    返回 {
      'bbox': (min_lat, min_lng, max_lat, max_lng),  # OSM 用的格式
      'center': (lng, lat),
      'radius_m': radius_m,
      'size_m': (h_m, w_m),   # bbox 对应米数
    }
    算法:
      1. 算 path 的 bbox (确保 path 在 bbox 内)
      2. 算米数 / 度
      3. 边缘 padding = min(radius_m, path 长度的 1/4)
         - 短 path (< 3.2km): 边缘 padding = radius_m
         - 长 path: padding 随 path 增长 (避免 bbox 太大 OSM 拒)
    """
    if not path:
        return {
            "bbox": (0.0, 0.0, 0.001, 0.001),
            "center": (0.0, 0.0),
            "radius_m": radius_m,
            "size_m": (0.0, 0.0),
        }
    # 1) 算 path 的 bbox
    lats = [p[1] for p in path]
    lngs = [p[0] for p in path]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    # 2) 中心点
    center_lat = (min_lat + max_lat) / 2
    center_lng = (min_lng + max_lng) / 2
    # 3) 算米数 / 度
    m_per_lat, m_per_lng = meters_per_degree(center_lat)
    # 4) path 长度 (米)
    path_h_m = (max_lat - min_lat) * m_per_lat
    path_w_m = (max_lng - min_lng) * m_per_lng
    path_len_m = max(path_h_m, path_w_m)
    # 5) padding: 限制 bbox 总大小, 避免 OSM 拒 (Overpass 限制 ~2km)
    # 目标: bbox 总长 <= 1500m (1.5km, 留点 margin)
    target_total_m = 1500.0
    if path_len_m + 2 * radius_m > target_total_m:
        # path 太长, padding 缩小
        padding_m = max((target_total_m - path_len_m) / 2, 100.0)
    else:
        padding_m = radius_m
    lat_pad = padding_m / m_per_lat
    lng_pad = padding_m / m_per_lng
    # 6) 加 pad
    bbox = (
        min_lat - lat_pad,
        min_lng - lng_pad,
        max_lat + lat_pad,
        max_lng + lng_pad,
    )
    h_m = (bbox[2] - bbox[0]) * m_per_lat
    w_m = (bbox[3] - bbox[1]) * m_per_lng
    return {
        "bbox": bbox,
        "center": (center_lng, center_lat),
        "radius_m": radius_m,
        "padding_m": padding_m,
        "size_m": (h_m, w_m),
    }


def lnglat_to_grid_cell(lng: float, lat: float,
                        bbox: Bbox, grid_size: Tuple[int, int]) -> Tuple[int, int]:
    """WGS84 (lng, lat) -> grid 坐标 (gx, gy)
    bbox: (min_lat, min_lng, max_lat, max_lng)
    grid_size: (w, h)
    """
    min_lat, min_lng, max_lat, max_lng = bbox
    w, h = grid_size
    if max_lat == min_lat or max_lng == min_lng:
        return (0, 0)
    nx = (lng - min_lng) / (max_lng - min_lng)
    # lat 大=北=grid 顶, 但 grid y=0 是顶, 翻转
    ny = 1.0 - (lat - min_lat) / (max_lat - min_lat)
    gx = int(nx * w)
    gy = int(ny * h)
    gx = max(0, min(w - 1, gx))
    gy = max(0, min(h - 1, gy))
    return (gx, gy)
