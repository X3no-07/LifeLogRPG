"""P0.4 自适应切片测试

核心: 验证 walking 段才切片, transit 段不爆 bbox
典型场景: 西单 -> 灵境胡同 (700m walking) -> 西二旗 (16.8km 地铁)
旧实现: bbox 16.8km -> OSM 拒/慢
新实现: bbox ~1.5km (只看 700m walking + 800m radius) + 1 个 transit_marker
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.schema import TransitMarker, LogPayload, Meta
from baker.core.tiling import slice_around_path, meters_per_degree, lnglat_to_grid_cell


# 测试用北京西单 -> 灵境胡同 -> 西二旗 真实坐标
# 西单 116.3736, 39.9075
# 灵境胡同 116.3820, 39.9115 (~700m walking)
# 西二旗 116.3068, 40.0461 (~16.8km 地铁)
XIDAN = (116.3736, 39.9075)
LINGJING = (116.3820, 39.9115)
XIERQI = (116.3068, 40.0461)


class TestTransitMarkerDataclass:
    """TransitMarker 数据契约"""

    def test_construction(self):
        tm = TransitMarker(
            name="西二旗", transport="transit",
            start_lng=LINGJING[0], start_lat=LINGJING[1],
            end_lng=XIERQI[0], end_lat=XIERQI[1],
            distance_m=16800.0, duration_sec=1800.0,
        )
        assert tm.name == "西二旗"
        assert tm.transport == "transit"
        assert tm.distance_m == 16800.0
        assert tm.duration_sec == 1800.0

    def test_to_dict_keys(self):
        tm = TransitMarker(name="X", transport="transit")
        d = tm.to_dict()
        for k in ["name", "transport", "start_lng", "start_lat", "end_lng", "end_lat",
                  "start_grid_x", "start_grid_y", "end_grid_x", "end_grid_y",
                  "distance_m", "duration_sec"]:
            assert k in d, f"missing key: {k}"

    def test_default_grid_coords_are_negative(self):
        """默认 grid 坐标是 -1 (越界/未投影)"""
        tm = TransitMarker(name="X", transport="transit")
        assert tm.start_grid_x == -1
        assert tm.end_grid_y == -1


class TestLogPayloadIncludesTransitMarkers:
    """LogPayload 必须能装 transit_markers 并 to_dict"""

    def test_empty_init(self):
        p = LogPayload()
        assert p.transit_markers == []

    def test_append_and_to_dict(self):
        p = LogPayload(meta=Meta(title="test"))
        p.transit_markers.append(TransitMarker(
            name="A", transport="transit",
            start_lng=116.0, start_lat=39.0,
            end_lng=116.5, end_lat=39.5,
        ))
        d = p.to_dict()
        assert "transit_markers" in d
        assert len(d["transit_markers"]) == 1
        assert d["transit_markers"][0]["name"] == "A"

    def test_to_dict_includes_pois_and_transit(self):
        """完整 to_dict 应包含 pois + transit_markers"""
        p = LogPayload()
        d = p.to_dict()
        assert "pois" in d
        assert "transit_markers" in d


class TestAdaptiveSliceBoundingBox:
    """核心: 长 transit 段不应让 bbox 爆掉"""

    def test_walking_only_small_bbox(self):
        """只 walking: bbox 跟 path 一致 + radius"""
        walking_pts = [XIDAN, LINGJING]   # 700m
        info = slice_around_path(walking_pts, radius_m=800)
        # 700m + 2*800 = 2300m -> 但 target_total_m=1500 限了, padding 自动收
        h_m, w_m = info["size_m"]
        # 短 path 应该有 padding
        assert max(h_m, w_m) <= 1600, f"bbox too large: {h_m}x{w_m}"

    def test_long_transit_does_not_blow_bbox(self):
        """旧实现: bbox ~ 16.8km
        新实现: 只用 walking_pts (西单->灵境胡同, 700m), bbox ~1.5km
        """
        # 模拟 text.py 做的事: 传 walking_pts (不包括 transit 段)
        walking_pts = [XIDAN, LINGJING]   # 只 700m walking
        info = slice_around_path(walking_pts, radius_m=800)
        h_m, w_m = info["size_m"]
        # bbox 必须在 1500m ± 100m (target_total_m 限制)
        assert max(h_m, w_m) <= 1700, f"bbox should be ~1.5km, got {h_m:.0f}x{w_m:.0f}"
        assert max(h_m, w_m) >= 1400, f"bbox too small: {h_m:.0f}x{w_m:.0f}"

    def test_old_waypoints_16km_bbox(self):
        """对比: 用旧方式 (all waypoints 包含 transit 端点) 确实会爆 16km
        证明我们没测错事 (新实现确实解决了 16km 爆 bbox)
        """
        # 模拟旧: 16.8km 直线 (西单 -> 西二旗)
        all_pts = [XIDAN, XIERQI]
        info = slice_around_path(all_pts, radius_m=800)
        h_m, w_m = info["size_m"]
        # 这确实会爆 (target_total_m 限到 1500m, 但 path 本身 16.8km, padding 几乎为 0)
        # 期望: bbox 等于 path 长度 (padding 缩到 100m)
        assert h_m > 10000, f"old way should give 16km bbox, got {h_m:.0f}"

    def test_bbox_size_m_uses_walking_only(self):
        """关键不变量: bbox 的 size_m 只反映 walking 段, 不反映 transit"""
        walking_only = slice_around_path([XIDAN, LINGJING], radius_m=800)
        all_including_transit = slice_around_path([XIDAN, LINGJING, XIERQI], radius_m=800)
        h_w, w_w = walking_only["size_m"]
        h_a, w_a = all_including_transit["size_m"]
        # walking 版本的 bbox 必须显著更小
        assert h_w < h_a / 2, f"walking bbox should be much smaller: w={h_w:.0f} vs a={h_a:.0f}"


class TestTransitMarkerGridProjection:
    """TransitMarker 的 grid 坐标投影 (clamp 到边缘)"""

    def test_within_bbox_normal(self):
        """端点都在 bbox 内 -> 正常 grid 坐标"""
        bbox = (39.90, 116.30, 39.95, 116.40)   # 西二旗附近
        tm = TransitMarker(
            name="西二旗", transport="transit",
            start_lng=116.35, start_lat=39.92,
            end_lng=116.37, end_lat=39.93,
        )
        # 手动调用 projection (跟 text.py 一样的逻辑)
        sx, sy = lnglat_to_grid_cell(tm.start_lng, tm.start_lat, bbox, (80, 60))
        ex, ey = lnglat_to_grid_cell(tm.end_lng, tm.end_lat, bbox, (80, 60))
        # 都在范围内
        assert 0 <= sx < 80
        assert 0 <= sy < 60
        assert 0 <= ex < 80
        assert 0 <= ey < 60

    def test_outside_bbox_clamps_to_edge(self):
        """端点超出 bbox -> clamp 到边缘 cell"""
        bbox = (39.90, 116.30, 39.92, 116.40)
        # 西二旗的 end 实际在 (116.3068, 40.0461) - 北边 0.126° 之外
        tm = TransitMarker(
            name="西二旗", transport="transit",
            start_lng=116.31, start_lat=39.91,
            end_lng=116.3068, end_lat=40.0461,  # 远超 bbox 北边界
        )
        ex, ey = lnglat_to_grid_cell(tm.end_lng, tm.end_lat, bbox, (80, 60))
        # lng=116.3068 紧贴 bbox 左边界 (116.30), 投影到左侧低列
        # lat=40.0461 远超 bbox 北 (39.92), clamp 到 y=0
        assert 0 <= ex < 10, f"ex should be near left edge, got {ex}"
        assert ey == 0, f"out-of-bbox lat should clamp to y=0, got {ey}"

    def test_both_outside_bbox_both_clamp(self):
        """两端都在 bbox 外 -> 都 clamp 到边缘"""
        bbox = (39.90, 116.30, 39.92, 116.40)
        # 完全在 bbox 外 (东 0.5°, 北 0.5°)
        tm = TransitMarker(
            name="FarPlace", transport="transit",
            start_lng=117.0, start_lat=40.0,
            end_lng=117.5, end_lat=40.5,
        )
        sx, sy = lnglat_to_grid_cell(tm.start_lng, tm.start_lat, bbox, (80, 60))
        ex, ey = lnglat_to_grid_cell(tm.end_lng, tm.end_lat, bbox, (80, 60))
        # 都 clamp 到 (79, 0) 东北角
        assert sx == 79
        assert sy == 0
        assert ex == 79
        assert ey == 0


class TestAdaptiveSliceWithMarkers:
    """集成测试: 模拟 text.py 的完整 walking_pts + transit_markers 流程"""

    def test_full_xidan_lingjing_xierqi_simulation(self):
        """完整模拟 西单 -> 灵境胡同 -> 西二旗 流程"""
        from baker.core.tiling import slice_around_path
        # 段 0: 西单 -> 灵境胡同, walking
        seg0_walking = [XIDAN, LINGJING]
        # 段 1: 灵境胡同 -> 西二旗, transit (transit 端点不在 walking_pts)
        seg1_transit_marker = TransitMarker(
            name="西二旗", transport="transit",
            start_lng=LINGJING[0], start_lat=LINGJING[1],
            end_lng=XIERQI[0], end_lat=XIERQI[1],
            distance_m=16800.0, duration_sec=1800.0,
        )
        # 切片只用 seg0 的 walking_pts
        slice_info = slice_around_path(seg0_walking, radius_m=800)
        h_m, w_m = slice_info["size_m"]
        # bbox 必须在 1.5km 上下 (而不是 16.8km)
        assert max(h_m, w_m) < 1700, f"expected ~1.5km bbox, got {h_m:.0f}x{w_m:.0f}"
        # transit_marker 仍然记录 16.8km 距离 (给 Godot 端 pin 显示)
        assert seg1_transit_marker.distance_m == 16800.0
        # 投影 transit 端点: 西二旗远在 bbox 北, clamp 到 y=0
        ex, ey = lnglat_to_grid_cell(seg1_transit_marker.end_lng, seg1_transit_marker.end_lat,
                                      slice_info["bbox"], (80, 60))
        seg1_transit_marker.end_grid_x = ex
        seg1_transit_marker.end_grid_y = ey
        # 西二旗的经度 (116.31) 在 bbox (116.36, 116.40) 之内, 但纬度 40.05 在 bbox (39.91, 39.92) 之外
        assert ey == 0, f"西二旗应该在 grid 北边缘, got ey={ey}"
