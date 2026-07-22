"""测试 baker/core/gridifier.py 的 OSM 相关函数"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.gridifier import (
    osm_to_grid, _draw_polygon, _draw_polyline_thick,
    _scanline_fill, _set_cell, _count_cells, _lnglat_to_grid_xy,
    CELL_GRASS, CELL_ROAD, CELL_BUILDING, CELL_WATER, CELL_TREE,
)


class TestLngLatToGrid:
    def test_basic(self):
        # 80x60 grid, bbox 北京天安门
        bbox = (39.906, 116.394, 39.917, 116.413)  # (min_lat, min_lng, max_lat, max_lng)
        # point (116.4, 39.91): nx=0.315, gx≈25; ny=0.6, gy≈36
        gx, gy = _lnglat_to_grid_xy(116.4, 39.91, bbox, (80, 60))
        assert 23 <= gx <= 27
        assert 34 <= gy <= 38

    def test_corner(self):
        bbox = (39.906, 116.394, 39.917, 116.413)
        # 西北角 (min_lat, min_lng) -> (0, 0) 实际因为翻转, (min_lat=底) -> 大 y
        # 实际上: lng=min=116.394 -> gx=0, lat=max=39.917 -> ny=0 -> gy=0 (顶)
        gx, gy = _lnglat_to_grid_xy(116.394, 39.917, bbox, (80, 60))
        assert gx == 0
        assert gy == 0

    def test_out_of_bounds_clamp(self):
        bbox = (39.906, 116.394, 39.917, 116.413)
        gx, gy = _lnglat_to_grid_xy(200, 100, bbox, (80, 60))
        assert gx == 79
        assert gy == 0  # ny=0 因为 lat 远大于 max


class TestSetCell:
    def test_in_bounds(self):
        g = [[0, 0, 0], [0, 0, 0]]
        _set_cell(g, 1, 1, 5)
        assert g[1][1] == 5

    def test_out_of_bounds(self):
        g = [[0, 0], [0, 0]]
        _set_cell(g, 5, 5, 1)  # 不崩
        _set_cell(g, -1, -1, 1)
        assert g == [[0, 0], [0, 0]]


class TestDrawPolylineThick:
    def test_simple(self):
        g = [[0] * 10 for _ in range(10)]
        # 水平线 (0, 5) -> (9, 5), thickness 1
        _draw_polyline_thick(g, [(0.0, 0.0), (9.0, 5.0)], (0, 0, 1, 1), (10, 10), 1, thickness=1)
        # 不崩, 至少有 road cell
        assert any(1 in row for row in g)

    def test_thickness_2(self):
        g = [[0] * 10 for _ in range(10)]
        # 垂直线, thickness 2
        _draw_polyline_thick(g, [(5.0, 0.0), (5.0, 9.0)], (0, 0, 1, 1), (10, 10), 1, thickness=2)
        # 应该画 2 列宽
        road_cells = sum(1 for row in g for c in row if c == 1)
        assert road_cells >= 5


class TestDrawPolygon:
    def test_square_fill(self):
        g = [[0] * 10 for _ in range(10)]
        # 4x4 正方形 (用 lat,lng 但 _draw_polygon 内部是 lng,lat)
        # 这里 bbox 中心=0,0 边长 1
        # 实际上 _draw_polygon 用 _lnglat_to_grid_xy, 假设 nodes=(lng, lat)
        # 构造 4 个顶点 (lng, lat): (0,0) (0,1) (1,1) (1,0)
        nodes = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
        # bbox 必须包含所有点: (0, 0, 1, 1)  (min_lat=0, min_lng=0, max_lat=1, max_lng=1)
        _draw_polygon(g, nodes, (0.0, 0.0, 1.0, 1.0), (10, 10), value=2, fill=True)
        # 中心应该是 2
        assert g[5][5] == 2

    def test_no_fill(self):
        g = [[0] * 10 for _ in range(10)]
        nodes = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
        _draw_polygon(g, nodes, (0.0, 0.0, 1.0, 1.0), (10, 10), value=2, fill=False)
        # 只有 4 边线被画, 中心还是 0
        assert g[5][5] == 0


class TestScanlineFill:
    def test_square_via_draw_polygon(self):
        """测 _draw_polygon (描轮廓 + fill), 矩形 (1,1) (3,1) (3,3) (1,3) 完整填充"""
        g = [[0] * 5 for _ in range(5)]
        nodes = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
        _draw_polygon(g, nodes, (0.0, 0.0, 4.0, 4.0), (5, 5), value=1, fill=True)
        # 内部点都应该是 1
        for y in range(1, 4):
            for x in range(1, 4):
                assert g[y][x] == 1, f"g[{y}][{x}] 应该是 1"
        # 外部应该是 0
        assert g[0][0] == 0
        assert g[4][4] == 0

    def test_polygon_no_fill(self):
        """测 _draw_polygon 描轮廓但不 fill (单线轮廓)"""
        g = [[0] * 7 for _ in range(7)]  # 大一点避免粗化
        nodes = [(2.0, 2.0), (4.0, 2.0), (4.0, 4.0), (2.0, 4.0)]
        _draw_polygon(g, nodes, (0.0, 0.0, 6.0, 6.0), (7, 7), value=1, fill=False, thickness=1)
        # 中心应该还是 0 (没 fill)
        assert g[3][3] == 0
        # 4 边中点应该是 1
        assert g[2][3] == 1  # 顶边中点
        assert g[4][3] == 1  # 底边中点
        assert g[3][2] == 1  # 左边中点
        assert g[3][4] == 1  # 右边中点


class TestOsmToGrid:
    def test_empty(self):
        parsed = {"roads": [], "buildings": [], "water": [], "green": []}
        grid, heights, info = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert info["road_count"] == 0
        assert all(c == CELL_GRASS for row in grid for c in row)
        # heights 全部 0
        assert all(v == 0 for row in heights for v in row)

    def test_road_and_building(self):
        # bbox 包含两个矩形
        # road 1: 水平线 y=2, x=0..9
        # building 1: 矩形 (2,5) (2,8) (5,8) (5,5)
        parsed = {
            "roads": [{"highway_type": "primary", "name": "长安街", "nodes": [(0.0, 0.8), (1.0, 0.8)]}],
            "buildings": [{"building": "yes", "name": "饭店", "levels": 2,
                           "nodes": [(0.3, 0.2), (0.3, 0.5), (0.6, 0.5), (0.6, 0.2)]}],
            "water": [],
            "green": [],
        }
        grid, heights, info = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert info["road_count"] == 1
        assert info["building_count"] == 1
        # 至少 1 个 road cell
        assert any(CELL_ROAD in row for row in grid)
        # 至少 1 个 cell 有 height > 0
        assert any(v > 0 for row in heights for v in row)
        # building cell 的 height 应该是 2
        for y in range(10):
            for x in range(10):
                if grid[y][x] == 2:  # building
                    assert heights[y][x] == 2
        # 至少 1 个 building cell
        assert any(CELL_BUILDING in row for row in grid)


class TestCountCells:
    def test_basic(self):
        g = [[0, 0, 1, 2], [0, 1, 1, 3], [2, 2, 2, 2]]
        counts = _count_cells(g)
        assert counts[0] == 3
        assert counts[1] == 3
        assert counts[2] == 5
        assert counts[3] == 1
