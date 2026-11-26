"""GCJ-02 <-> WGS84 坐标转换 (eviltransform 算法, 仅标准库)

背景:
- 高德地图 API (geocode / place / route) 返回的都是 GCJ-02 坐标
- OSM / Overpass 返回的是 WGS84 坐标
- 两者在国内相差约 50-500m; 之前仓库直接接受这个误差, 不做转换
- 现在烘焙管线统一用 WGS84: 高德来的点在进切片/投影前转成 WGS84,
  只有调高德 API 本身时 (route 入参、place_around 中心点) 才保持 GCJ-02

算法: eviltransform (https://github.com/googollee/eviltransform),
  GCJ-02 -> WGS84 用正变换残差迭代两次逼近, 往返误差 < 1e-6 度 (约 0.1m)。
"""
import math

_PI = math.pi
_A = 6378245.0                    # 克拉索夫斯基椭球长半轴 (米)
_EE = 0.00669342162296594323       # 偏心率平方


def out_of_china(lng: float, lat: float) -> bool:
    """中国境外没有 GCJ-02 偏移, 直接返回原坐标"""
    return lng < 72.004 or lng > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(lng: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat \
        + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * _PI) + 20.0 * math.sin(2.0 * lng * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * _PI) + 40.0 * math.sin(lat / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * _PI) + 320 * math.sin(lat * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng \
        + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * _PI) + 20.0 * math.sin(2.0 * lng * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * _PI) + 40.0 * math.sin(lng / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * _PI) + 300.0 * math.sin(lng / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def _delta(lng: float, lat: float) -> tuple:
    """(lng, lat) 处 GCJ-02 相对 WGS84 的偏移量 (度)"""
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * _PI
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    dlng = (dlng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * _PI)
    return dlng, dlat


def wgs84_to_gcj02(lng: float, lat: float) -> tuple:
    """WGS84 -> GCJ-02 (调高德 API 前用, 如 place_around 的中心点)"""
    if out_of_china(lng, lat):
        return (lng, lat)
    dlng, dlat = _delta(lng, lat)
    return (lng + dlng, lat + dlat)


def gcj02_to_wgs84(lng: float, lat: float) -> tuple:
    """GCJ-02 -> WGS84 (高德返回的点进烘焙管线前用)

    迭代两次逼近: 先用一次逆推得初值, 再用正变换的残差修正,
    往返误差 < 1e-6 度 (约 0.1m)。
    """
    if out_of_china(lng, lat):
        return (lng, lat)
    wlng, wlat = lng, lat
    for _ in range(2):
        glng, glat = wgs84_to_gcj02(wlng, wlat)
        wlng += lng - glng
        wlat += lat - glat
    return (wlng, wlat)


def gcj02_to_wgs84_points(points) -> list:
    """批量转换 [(lng, lat), ...] (GCJ-02 -> WGS84), 用于 route polyline"""
    return [gcj02_to_wgs84(lng, lat) for lng, lat in points]
