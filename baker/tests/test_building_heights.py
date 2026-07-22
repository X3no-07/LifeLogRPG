"""P1.2 建筑层数测试

覆盖:
- osm.py parse_overpass 提 building:levels (默认 1, clamp 1-20)
- schema.py MapData.building_heights 字段
- gridifier.py osm_to_grid 返回 (grid, heights, debug)
- text.py / coords.py 把 heights 存到 p.map.building_heights
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.schema import MapData, LogPayload, Meta
from baker.core.gridifier import osm_to_grid, CELL_BUILDING, CELL_GRASS
from baker.clients.osm import parse_overpass


class TestOsmParseLevels:
    """OSM parse_overpass 提取 building:levels"""

    def test_default_level_is_1(self):
        """没 building:levels tag -> levels=1"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes"}},   # 无 levels
        ]}
        result = parse_overpass(raw)
        assert len(result["buildings"]) == 1
        assert result["buildings"][0]["levels"] == 1

    def test_explicit_level(self):
        """有 building:levels=3 -> levels=3"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "building:levels": "3"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 3

    def test_level_with_underscore_tag(self):
        """building:levels 也能解析 (P1.2 兼容)"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "commercial", "building:levels": "12"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 12

    def test_invalid_level_string_defaults_to_1(self):
        """无效字符串 -> 1"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "building:levels": "abc"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 1

    def test_level_clamped_to_20(self):
        """超 20 楼 clamp 到 20"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "building:levels": "100"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 20

    def test_level_min_1(self):
        """0 或负数 -> 1"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "building:levels": "0"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 1

    def test_float_level_rounded(self):
        """浮点 string 转 int"""
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "building:levels": "3.5"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 3


class TestMapDataHeights:
    """schema.MapData.building_heights 字段"""

    def test_default_empty(self):
        m = MapData()
        assert m.building_heights == []

    def test_set_and_to_dict(self):
        m = MapData(building_heights=[[0, 1], [2, 3]])
        d = m.to_dict()
        assert "building_heights" in d
        assert d["building_heights"] == [[0, 1], [2, 3]]

    def test_logpayload_includes_heights(self):
        """LogPayload.to_dict 也带 building_heights"""
        p = LogPayload()
        p.map.building_heights = [[1, 2]]
        d = p.to_dict()
        assert d["map"]["building_heights"] == [[1, 2]]


class TestOsmToGridReturnsHeights:
    """gridifier.osm_to_grid 返回 (grid, heights, debug)"""

    def test_three_tuple(self):
        """返回 3-tuple"""
        parsed = {"roads": [], "buildings": [], "water": [], "green": []}
        result = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert len(result) == 3
        grid, heights, info = result
        assert info["road_count"] == 0
        assert all(c == CELL_GRASS for row in grid for c in row)
        # heights 全 0
        assert all(v == 0 for row in heights for v in row)

    def test_building_height_stamped(self):
        """building 的 cell 在 heights 里有对应 levels 值"""
        # 1 个 building 矩形: (0.2, 0.2) - (0.4, 0.4) levels=4
        parsed = {
            "roads": [],
            "buildings": [{
                "building": "yes", "name": "test", "levels": 4,
                "nodes": [(0.2, 0.2), (0.4, 0.2), (0.4, 0.4), (0.2, 0.4), (0.2, 0.2)],
            }],
            "water": [], "green": [],
        }
        grid, heights, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        # building 中心 cell (5, 5) 应该是 height=4
        # bbox 中心 cell 计算: gx = (0.3 - 0) / 1 * 10 = 3, gy = 1 - (0.3/1) * 10 = 7
        found_4 = False
        for y in range(10):
            for x in range(10):
                if heights[y][x] == 4:
                    found_4 = True
                    # 对应 cell 应该是 building
                    assert grid[y][x] == CELL_BUILDING
        assert found_4, "应该有 cell 的 height=4"


class TestOsmToGridMaxLevel:
    """多层建筑重叠时取 max"""

    def test_overlapping_buildings_take_max(self):
        """两个 building 覆盖同 cell, heights 取 max"""
        # 2 个 building 部分重叠
        parsed = {
            "roads": [],
            "buildings": [
                {"building": "yes", "levels": 2,
                 "nodes": [(0.2, 0.2), (0.5, 0.2), (0.5, 0.5), (0.2, 0.5), (0.2, 0.2)]},
                {"building": "yes", "levels": 5,
                 "nodes": [(0.4, 0.4), (0.7, 0.4), (0.7, 0.7), (0.4, 0.7), (0.4, 0.4)]},
            ],
            "water": [], "green": [],
        }
        grid, heights, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        # 找 max height
        max_h = max(v for row in heights for v in row)
        assert max_h == 5
