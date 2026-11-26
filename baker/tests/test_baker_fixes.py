"""新修法测试: 楼快栅格化 + 路不断 + 路线贴路 + 地面分类型

覆盖 (baker 源代码改动, 不针对某一座城):
- osm.py: building:part 也算楼; 地面类型分类 (grass/plaza/parking/dirt)
- gridifier.py osm_to_grid: PIL 填多边形、楼后画 (路不切楼)、
  开放水道画线不填面、ground 在时默认铺装
- gridifier.py densify_and_snap_route: 加密 + 吸附到 OSM 路中心线
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.gridifier import (
    osm_to_grid, densify_and_snap_route,
    CELL_GRASS, CELL_ROAD, CELL_BUILDING, CELL_WATER, CELL_TREE, CELL_PLAZA,
)
from baker.clients.osm import parse_overpass


def _nodes(*pts):
    """(lng, lat) 点列 -> parse_overpass 用的 raw elements。"""
    els = []
    for i, (lng, lat) in enumerate(pts, start=1):
        els.append({"type": "node", "id": i, "lat": lat, "lon": lng})
    return els


def _way(wid, node_ids, tags):
    return {"type": "way", "id": wid, "nodes": node_ids, "tags": tags}


def _seg_dist(px, py, ax, ay, bx, by):
    """点到线段距离 (测试里验路线贴路用)。"""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    s2 = vx * vx + vy * vy
    t = 0.0 if s2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / s2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


class TestBuildingPart:
    """building:part 碎片也算楼 (故宫中和殿只有碎片、没有整栋)。"""

    def test_part_is_building(self):
        raw = {"elements": _nodes((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)) + [
            _way(100, [1, 2, 3, 4, 1], {"building:part": "yes", "name": "中和殿"}),
        ]}
        result = parse_overpass(raw)
        assert len(result["buildings"]) == 1
        b = result["buildings"][0]
        assert b["name"] == "中和殿"
        assert b["part"] is True
        assert b["levels"] == 1  # 默认 1

    def test_part_with_levels(self):
        raw = {"elements": _nodes((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)) + [
            _way(100, [1, 2, 3, 4, 1],
                 {"building:part": "yes", "building:levels": "3"}),
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["levels"] == 3

    def test_part_drawn_on_grid(self):
        """building:part 的楼在 grid 里有 building 格子, 不缺失。"""
        parsed = {
            "roads": [], "water": [], "green": [], "ground": [],
            "buildings": [{"building": "yes", "name": "中和殿", "levels": 1,
                           "part": True,
                           "nodes": [(0.3, 0.3), (0.3, 0.6), (0.6, 0.6), (0.6, 0.3)]}],
        }
        grid, heights, info = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert info["building_count"] == 1
        n_b = sum(1 for row in grid for c in row if c == CELL_BUILDING)
        assert n_b >= 4, f"中和殿应有 >=4 个 building 格子, 实际 {n_b}"


class TestGroundClassification:
    """parse_overpass 的地面类型分类。"""

    def test_ground_kinds(self):
        els = _nodes((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0),
                     (2.0, 2.0), (2.0, 3.0), (3.0, 3.0), (3.0, 2.0))
        raw = {"elements": els + [
            _way(1, [1, 2, 3, 4, 1], {"landuse": "meadow"}),        # 草
            _way(2, [1, 2, 3, 4, 1], {"highway": "pedestrian"}),    # 广场 (闭合)
            _way(3, [1, 2, 3, 4, 1], {"amenity": "parking"}),       # 停车场
            _way(4, [1, 2, 3, 4, 1], {"landuse": "brownfield"}),    # 裸土
            _way(5, [1, 2, 3, 4], {"landuse": "grass"}),            # 开放线, 不是地面
        ]}
        result = parse_overpass(raw)
        kinds = sorted(g["kind"] for g in result["ground"])
        assert kinds == ["dirt", "grass", "parking", "plaza"], kinds
        # 闭合人行道同时也是路
        assert len(result["roads"]) == 1
        assert result["roads"][0]["highway_type"] == "pedestrian"

    def test_green_still_classified(self):
        """park 既是绿化 (树) 也是地面 (草), 两边都有。"""
        raw = {"elements": _nodes((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)) + [
            _way(1, [1, 2, 3, 4, 1], {"leisure": "park"}),
        ]}
        result = parse_overpass(raw)
        assert len(result["green"]) == 1
        assert any(g["kind"] == "grass" for g in result["ground"])


class TestOsmToGridDrawOrder:
    """楼后画: 路不再切楼; 水上画路: 过河是桥。"""

    def test_building_not_cut_by_road(self):
        """一条路穿过楼的范围, 楼的格子要完整 (旧顺序路后画会切楼)。"""
        parsed = {
            "roads": [{"highway_type": "primary", "name": "大街",
                       "nodes": [(0.0, 0.65), (1.0, 0.65)]}],
            "buildings": [{"building": "yes", "name": "大殿", "levels": 2,
                           "nodes": [(0.3, 0.2), (0.3, 0.5), (0.6, 0.5), (0.6, 0.2)]}],
            "water": [], "green": [],
        }
        grid, heights, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        # 楼中心 (gx 4-5, gy 6-7) 必须是 building (路在 lat 0.65 -> gy 3-4, 不穿楼心;
        # 换一条穿楼心的路再验)
        assert grid[6][4] == CELL_BUILDING
        assert grid[7][5] == CELL_BUILDING
        # 楼外面的路还在
        assert grid[3][1] == CELL_ROAD

    def test_road_through_building_keeps_building(self):
        """路直线穿过楼体时, 楼体格子不被路切断 (楼后画)。"""
        parsed = {
            "roads": [{"highway_type": "footway", "name": "人行道",
                       "nodes": [(0.0, 0.35), (1.0, 0.35)]}],
            "buildings": [{"building": "yes", "name": "大殿", "levels": 2,
                           "nodes": [(0.3, 0.2), (0.3, 0.5), (0.6, 0.5), (0.6, 0.2)]}],
            "water": [], "green": [],
        }
        grid, heights, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        # lat 0.35 -> gy = (1-0.35)*10 = 6 (路穿过楼的 gy 5-8 范围)
        # 楼中心格子仍要是 building
        assert grid[6][4] == CELL_BUILDING
        assert grid[6][5] == CELL_BUILDING
        # 楼外的路还在
        assert grid[6][1] == CELL_ROAD
        assert grid[6][8] == CELL_ROAD

    def test_road_bridge_over_water(self):
        """路画在水上: 湖中间的路格子是路 (桥), 湖其他格子是水。"""
        parsed = {
            "roads": [{"highway_type": "residential", "name": "桥路",
                       "nodes": [(0.0, 0.5), (1.0, 0.5)]}],
            "buildings": [],
            "water": [{"type": "lake", "name": "湖",
                       "nodes": [(0.2, 0.3), (0.2, 0.7), (0.5, 0.7), (0.5, 0.3), (0.2, 0.3)]}],
            "green": [],
        }
        grid, heights, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        # lat 0.5 -> gy 5; 湖 gx 2-5, gy 3-7 (PIL 填面不含右/下边, 实际约 gx 2-4, gy 3-6)
        assert grid[5][3] == CELL_ROAD, "湖心的路应是桥 (CELL_ROAD)"
        assert grid[4][3] == CELL_WATER
        assert grid[6][3] == CELL_WATER
        # 湖外的路还在
        assert grid[5][1] == CELL_ROAD
        assert grid[5][8] == CELL_ROAD

    def test_open_river_is_line_not_lake(self):
        """开放河道 (不闭合) 只画一条线, 不能填成一片湖。
        旧 _draw_polygon 会把开放线闭合填面, 一条河能占半张图。"""
        parsed = {
            "roads": [], "buildings": [], "green": [],
            "water": [{"type": "river", "name": "河",
                       "nodes": [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5)]}],
        }
        grid, heights, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        n_w = sum(1 for row in grid for c in row if c == CELL_WATER)
        # 线宽 2 x 长 ~8 格 = ~16-24 格; 填面会是 40+ 格
        assert 0 < n_w <= 30, f"开放河道应是窄线 (~16-24 格), 实际 {n_w} 格"
        # 水格子都集中在 gy 4-6 (lat 0.5 附近)
        for y in range(10):
            for x in range(10):
                if grid[y][x] == CELL_WATER:
                    assert 4 <= y <= 6, f"水格子应在河线附近, 实际 ({x},{y})"


class TestGroundDefault:
    """地面默认: 有 ground 数据时默认铺装, 没有时默认草地 (兼容旧调用)。"""

    def test_default_paved_when_ground_present(self):
        parsed = {"roads": [], "buildings": [], "water": [], "green": [], "ground": []}
        grid, _, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert all(c == CELL_PLAZA for row in grid for c in row)

    def test_default_grass_when_ground_absent(self):
        parsed = {"roads": [], "buildings": [], "water": [], "green": []}
        grid, _, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert all(c == CELL_GRASS for row in grid for c in row)

    def test_grass_ground_area_is_grass(self):
        """OSM 标了草地的区域画草, 其他地方铺装。"""
        parsed = {
            "roads": [], "buildings": [], "water": [], "green": [],
            "ground": [{"kind": "grass",
                        "nodes": [(0.0, 0.0), (0.0, 0.5), (0.5, 0.5), (0.5, 0.0)]}],
        }
        grid, _, _ = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        # 草地区域 (lng<0.5, lat<0.5 -> gx<5, gy>5) 应是草
        assert grid[8][2] == CELL_GRASS
        # 其他地方铺装
        assert grid[2][8] == CELL_PLAZA


class TestDensifyAndSnapRoute:
    """路线加密 + 吸附到 OSM 路中心线。"""

    def test_densify_gap(self):
        """没路可吸附时也加密: 相邻点间距短 (浮点 <=2 格; 转整数格后
        四舍五入最多到 ~2.8, 仍是密点, 不会 11 格一跳)。"""
        route = [(0.1, 0.1), (0.9, 0.9)]
        out = densify_and_snap_route(route, [], (0, 0, 1, 1), (10, 10))
        assert len(out) >= 5, f"应加密到 >=5 个点, 实际 {len(out)}"
        for a, b in zip(out, out[1:]):
            d = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            assert d <= 3.0, f"相邻点间距 {d} > 3 格"
        # 起点终点对得上
        assert out[0] == {"x": 1, "y": 9}
        assert out[-1] == {"x": 9, "y": 1}

    def test_snap_to_road_corner(self):
        """直线切角时吸附到 L 形路中心线, 不再走对角线。"""
        # 路是 L 形: (0.1,0.1)->(0.5,0.1)->(0.5,0.9)->(0.9,0.9)
        # 直线 (0.1,0.1)->(0.9,0.9) 会切角穿过中间
        route = [(0.1, 0.1), (0.9, 0.9)]
        roads = [{"highway_type": "residential", "name": "L路",
                  "nodes": [(0.1, 0.1), (0.5, 0.1), (0.5, 0.9), (0.9, 0.9)]}]
        out = densify_and_snap_route(route, roads, (0, 0, 1, 1), (10, 10))
        # 路的折线 (grid 坐标): (1,9)->(5,9)->(5,1)->(9,1)
        road_segs = [((1, 9), (5, 9)), ((5, 9), (5, 1)), ((5, 1), (9, 1))]
        for wp in out:
            d = min(_seg_dist(wp["x"], wp["y"], a[0], a[1], b[0], b[1])
                    for a, b in road_segs)
            assert d <= 1.5, f"路点 {wp} 离路中心线 {d:.1f} 格, 应贴路走"
        # 中间应经过拐角附近 (5,9) 或 (5,1), 而不是只走对角线
        assert any(wp["x"] == 5 for wp in out), "应经过 L 形拐角 x=5"

    def test_single_point(self):
        out = densify_and_snap_route([(0.5, 0.5)], [], (0, 0, 1, 1), (10, 10))
        assert out == [{"x": 5, "y": 5}]

    def test_empty_route(self):
        assert densify_and_snap_route([], [], (0, 0, 1, 1), (10, 10)) == []
