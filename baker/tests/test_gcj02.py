"""测试 baker/core/gcj02.py GCJ-02 <-> WGS84 转换

eviltransform 一次逆推近似: 往返误差应 < 1e-6 度 (约 0.1m)。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.gcj02 import (
    gcj02_to_wgs84, wgs84_to_gcj02, gcj02_to_wgs84_points, out_of_china,
)

# 北京的点 (GCJ-02 坐标, 天安门 / 西单 / 国贸附近)
BEIJING_GCJ = [
    (116.39750, 39.90870),   # 天安门附近
    (116.36600, 39.90800),   # 西单附近
    (116.45500, 39.90850),   # 国贸附近
    (116.31600, 39.99000),   # 中关村附近
    (121.47370, 31.23040),   # 上海人民广场 (跨城市对照)
]


def _deg_to_m(dlng: float, dlat: float, lat: float) -> float:
    """经纬度差 (度) 换算成米 (近似)"""
    return math.hypot(dlng * 111320 * math.cos(math.radians(lat)), dlat * 110540)


class TestRoundTrip:
    def test_gcj_to_wgs84_and_back(self):
        for lng, lat in BEIJING_GCJ:
            wlng, wlat = gcj02_to_wgs84(lng, lat)
            blng, blat = wgs84_to_gcj02(wlng, wlat)
            assert abs(blng - lng) < 1e-6, f"{lng},{lat} round-trip lng err {blng - lng}"
            assert abs(blat - lat) < 1e-6, f"{lng},{lat} round-trip lat err {blat - lat}"

    def test_wgs84_to_gcj02_and_back(self):
        for lng, lat in BEIJING_GCJ:
            wlng, wlat = gcj02_to_wgs84(lng, lat)  # 先拿到对应的 WGS84
            glng, glat = wgs84_to_gcj02(wlng, wlat)
            wlng2, wlat2 = gcj02_to_wgs84(glng, glat)
            assert abs(wlng2 - wlng) < 1e-6
            assert abs(wlat2 - wlat) < 1e-6

    def test_offset_is_real_in_china(self):
        """国内转换必须真的移动坐标 (偏移几十到几百米), 不是原样返回"""
        for lng, lat in BEIJING_GCJ:
            wlng, wlat = gcj02_to_wgs84(lng, lat)
            off_m = _deg_to_m(wlng - lng, wlat - lat, lat)
            assert 10.0 < off_m < 1000.0, f"{lng},{lat} offset {off_m:.1f}m 不在预期范围"

    def test_out_of_china_identity(self):
        # 境外无偏移, 原样返回
        assert gcj02_to_wgs84(139.7670, 35.6812) == (139.7670, 35.6812)  # 东京
        assert wgs84_to_gcj02(-0.1278, 51.5074) == (-0.1278, 51.5074)   # 伦敦
        assert out_of_china(139.7670, 35.6812) is True
        assert out_of_china(116.3975, 39.9087) is False

    def test_batch_points(self):
        pts = gcj02_to_wgs84_points(BEIJING_GCJ)
        assert len(pts) == len(BEIJING_GCJ)
        for (lng, lat), (wlng, wlat) in zip(BEIJING_GCJ, pts):
            assert (wlng, wlat) == gcj02_to_wgs84(lng, lat)
