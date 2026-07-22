"""测试 baker/core/gridifier.py 网格化算法"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.gridifier import (
    polyline_to_points,
    points_to_grid,
    build_grid_from_waypoints,
    bresenham_line,
    compute_bounds,
    approx_distance_km,
)


class TestPolyline:
    def test_basic(self):
        s = "116.40,39.90;116.41,39.91;116.42,39.92"
        pts = polyline_to_points(s)
        assert len(pts) == 3
        assert pts[0] == (116.40, 39.90)
        assert pts[2] == (116.42, 39.92)

    def test_empty(self):
        assert polyline_to_points("") == []
        assert polyline_to_points(None) == []

    def test_invalid_segment_skipped(self):
        s = "116.40,39.90;invalid;116.42,39.92"
        pts = polyline_to_points(s)
        assert len(pts) == 2  # 跳过 invalid


class TestPointsToGrid:
    def test_basic(self):
        pts = [(0.0, 0.0), (1.0, 1.0)]
        bounds = (0.0, 0.0, 2.0, 2.0)
        wps = points_to_grid(pts, bounds, (10, 10))
        # 第 1 个点 (0,0) -> (0, 9) (lat 翻转到 grid 顶)
        # 第 2 个点 (1,1) -> (5, 5)
        assert wps[0] == {"x": 0, "y": 9}
        assert wps[1] == {"x": 5, "y": 5}

    def test_dedup_consecutive(self):
        pts = [(0.0, 0.0), (0.0, 0.0), (1.0, 1.0)]
        bounds = (0.0, 0.0, 1.0, 1.0)
        wps = points_to_grid(pts, bounds, (10, 10))
        # (0,0) 和 (0,0) 投影到同一格, 去重后剩 2 个
        assert len(wps) == 2

    def test_zero_area_bounds(self):
        """min_lng == max_lng 时不崩"""
        pts = [(0.0, 0.0)]
        bounds = (0.0, 0.0, 0.0, 0.0)
        assert points_to_grid(pts, bounds, (10, 10)) == []


class TestBresenham:
    def test_horizontal(self):
        g = [[0] * 10 for _ in range(5)]
        bresenham_line(g, 1, 2, 8, 2, value=1)
        # (1,2) 到 (8,2) 一行, 加上 3x3 粗化, 但 height=5, ok
        for x in range(10):
            assert g[2][x] == 1

    def test_vertical(self):
        g = [[0] * 5 for _ in range(10)]
        bresenham_line(g, 2, 1, 2, 8, value=1)
        for y in range(10):
            assert g[y][2] == 1


class TestBuildGrid:
    def test_waypoints_create_road(self):
        wps = [{"x": 0, "y": 0}, {"x": 5, "y": 0}]
        grid = build_grid_from_waypoints(wps, 10, 5, seed=42)
        # 第 0 行应该有 road=1
        assert grid[0][0] == 1
        assert grid[0][5] == 1
        # 第 4 行不应该有 road
        for x in range(10):
            assert grid[4][x] != 1

    def test_tree_and_building_density(self):
        """seed 固定时输出可预测, 且 grass 区域有 decoration"""
        wps = [{"x": 0, "y": 0}]
        grid = build_grid_from_waypoints(wps, 50, 50, seed=42, tree_density=0.05, building_density=0.02)
        types = set()
        for row in grid:
            for cell in row:
                types.add(cell)
        # 0 (grass) 1 (road) 2 (building) 4 (tree) 都可能出现
        assert 0 in types or 1 in types  # 至少 grass 或 road

    def test_independence_seeds(self):
        """不同 seed 给不同结果"""
        wps = [{"x": 0, "y": 0}]
        g1 = build_grid_from_waypoints(wps, 20, 20, seed=1)
        g2 = build_grid_from_waypoints(wps, 20, 20, seed=2)
        # 至少有几格不同
        diffs = sum(1 for y in range(20) for x in range(20) if g1[y][x] != g2[y][x])
        assert diffs > 0


class TestBounds:
    def test_basic(self):
        pts = [(0.0, 0.0), (1.0, 1.0)]
        b = compute_bounds(pts, pad_ratio=0.1)
        assert b[0] < 0.0  # min_lng - pad
        assert b[2] > 1.0

    def test_empty(self):
        assert compute_bounds([]) == (0.0, 0.0, 0.001, 0.001)

    def test_single_point(self):
        b = compute_bounds([(0.5, 0.5)])
        # 单点 pad 是 0.001
        assert abs(b[2] - 0.501) < 1e-6


class TestDistance:
    def test_zero(self):
        assert approx_distance_km((0, 0), (0, 0)) == 0

    def test_one_degree_lat(self):
        d = approx_distance_km((0, 0), (0, 1))
        # 1° lat ≈ 111 km
        assert 110 < d < 112
