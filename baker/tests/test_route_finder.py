"""沿路网寻路测试: 锚点吸附 + A* 沿路走 + 加密 (baker 源代码改动, 不针对某一座城)

覆盖 (baker/core/gridifier.py 新增):
- _route_cell_cost: 路/广场/人行道 1, 草 20, 树 40, 楼/水/POI 不可走
- snap_to_passable: 最近的可走格 (BFS, 不限半径)
- find_path_on_grid: A* 八方向 + 斜走不切角, 全程不进楼不进水
- route_along_roads: 锚点吸附 + 逐段 A* + 加密成路线点
- apply_path_overlay: 路线叠到已有网格上 (osm_to_grid 第 6 步同款)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.clients.osm import parse_overpass
from baker.core.gridifier import (
    osm_to_grid, densify_and_snap_route,
    _route_cell_cost, snap_to_passable, find_path_on_grid,
    route_along_roads, apply_path_overlay, split_transport_at_gate,
    smooth_path_on_grid, _segment_crosses_blocked, _straight_line_cells,
    CELL_GRASS, CELL_ROAD, CELL_BUILDING, CELL_WATER, CELL_TREE,
    CELL_SIDEWALK, CELL_PLAZA,
)

_CH = {".": CELL_GRASS, "r": CELL_ROAD, "B": CELL_BUILDING,
       "w": CELL_WATER, "p": CELL_PLAZA, "t": CELL_TREE, "s": CELL_SIDEWALK}


def _grid(*rows):
    """字符串行 -> grid。'.' 草, 'r' 路, 'B' 楼, 'w' 水, 'p' 广场, 't' 树, 's' 人行道。"""
    return [[_CH[c] for c in row] for row in rows]


def _all_passable(grid, path):
    """路径上每点都可走 (代价不是 None)。"""
    return all(_route_cell_cost(grid[y][x]) is not None for x, y in path)


class TestRouteCellCost:
    def test_costs(self):
        assert _route_cell_cost(CELL_ROAD) == 1.0
        assert _route_cell_cost(CELL_PLAZA) == 5.0
        assert _route_cell_cost(CELL_SIDEWALK) == 1.0
        assert _route_cell_cost(CELL_GRASS) == 20.0
        assert _route_cell_cost(CELL_TREE) == 40.0
        assert _route_cell_cost(CELL_BUILDING) is None
        assert _route_cell_cost(CELL_WATER) is None
        assert _route_cell_cost(6) is None  # POI 标记不可走


class TestSnapToPassable:
    def test_already_passable(self):
        g = _grid("rrr", "rrr", "rrr")
        assert snap_to_passable(g, 1, 1) == (1, 1)

    def test_inside_building_snaps_to_road(self):
        g = _grid("rrrrr",
                  "rBBBr",
                  "rBBBr",
                  "rBBBr",
                  "rrrrr")
        # (2,2) 在楼里, 最近的可走格距离 2 (上下左右都是楼, 再外一圈是路)
        x, y = snap_to_passable(g, 2, 2)
        assert g[y][x] == CELL_ROAD
        assert abs(x - 2) + abs(y - 2) == 2

    def test_out_of_bounds_clamped(self):
        g = _grid("rrr", "rrr", "rrr")
        assert snap_to_passable(g, -5, 99) == (0, 2)

    def test_all_blocked_returns_clamped(self):
        g = _grid("BBB", "BBB", "BBB")
        assert snap_to_passable(g, 1, 1) == (1, 1)


class TestFindPathOnGrid:
    def test_straight_road(self):
        g = _grid("..........",
                  "rrrrrrrrrr",
                  "..........")
        path = find_path_on_grid(g, (0, 1), (9, 1))
        assert path[0] == (0, 1) and path[-1] == (9, 1)
        assert _all_passable(g, path)
        # 沿路直走, 不绕远: 长度就是 10 格
        assert len(path) == 10

    def test_building_wall_with_gap(self):
        # 楼墙横在中间, 只有 x=5 处留一个路口
        g = _grid("rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "BBBBBrBBBB",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr")
        path = find_path_on_grid(g, (0, 0), (9, 4))
        assert path[0] == (0, 0) and path[-1] == (9, 4)
        assert _all_passable(g, path)
        assert all(g[y][x] != CELL_BUILDING for x, y in path)
        # 必须经过缺口 (5, 2)
        assert (5, 2) in path

    def test_water_with_bridge(self):
        # 河横贯, 只有 x=2 处一座桥 (路格子)
        g = _grid("rrrrrrrrrr",
                  "wwwwrwwwww",
                  "rrrrrrrrrr")
        path = find_path_on_grid(g, (0, 0), (9, 2))
        assert _all_passable(g, path)
        assert all(g[y][x] != CELL_WATER for x, y in path)
        assert (4, 1) in path  # 过桥 (桥在 x=4)

    def test_prefers_road_over_grass(self):
        # 直线是草地, 绕路是路: A* 应选路 (草代价 4, 绕路代价低)
        g = _grid("rrrrrrrrrr",
                  "..........",
                  "rrrrrrrrrr")
        path = find_path_on_grid(g, (0, 0), (9, 0))
        assert path == [(x, 0) for x in range(10)]

    def test_no_diagonal_corner_cut(self):
        # 两栋楼斜对角相邻, 斜穿过去会从楼角切过; 必须绕
        g = _grid("rrB.",
                  "rBB.",
                  "rrrr")
        # (1,0) -> (2,2): 直线斜穿会经过楼角; A* 应绕开
        path = find_path_on_grid(g, (1, 0), (2, 2))
        assert _all_passable(g, path)
        assert all(g[y][x] != CELL_BUILDING for x, y in path)

    def test_start_equals_end(self):
        g = _grid("rrr", "rrr", "rrr")
        assert find_path_on_grid(g, (1, 1), (1, 1)) == [(1, 1)]

    def test_only_way_is_through_water(self):
        # 起终点各自孤立在水里 (除起终点外全是水, 无路可走):
        # 楼/水可高价穿 (500/格), A* 仍能找到路 (穿水过去), 不会空手而归
        g = _grid("rwwww",
                  "wwwww",
                  "wwwww",
                  "wwwww",
                  "wwwwr")
        path = find_path_on_grid(g, (0, 0), (4, 4))
        assert path[0] == (0, 0) and path[-1] == (4, 4)
        assert len(path) > 1  # 穿水找到路, 不为空

    def test_prefers_road_detour_over_wide_building(self):
        # 宽楼横在中间, 绕路是路: 宁绕远 (路代价 1) 不穿大殿 (500/格)
        g = _grid("rrrrrrrrrr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rBBBBBBBBBr",
                  "rrrrrrrrrr")
        path = find_path_on_grid(g, (0, 0), (9, 0))
        assert path == [(x, 0) for x in range(10)]  # 沿顶路直走, 不穿楼

    def test_crosses_thin_wall_at_road_marked_gate(self):
        # 楼墙横在中间, 只有 x=5 处是门洞 (road_mask 标为有路穿过):
        # A* 应从门洞过 (20/格), 不从别处穿墙 (500/格)
        g = _grid("rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "BBBBBBBBBB",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr")
        mask = {(5, 2)}  # 门洞: 只有 (5,2) 有路穿过
        path = find_path_on_grid(g, (0, 0), (9, 4), road_mask=mask)
        assert path[0] == (0, 0) and path[-1] == (9, 4)
        assert (5, 2) in path  # 必须经过门洞
        # 穿墙只穿 1 格 (门洞), 其余全是路
        assert sum(1 for x, y in path if g[y][x] == CELL_BUILDING) == 1


class TestAstarCellCost:
    def test_costs(self):
        from baker.core.gridifier import _astar_cell_cost
        assert _astar_cell_cost(CELL_ROAD) == 1.0
        assert _astar_cell_cost(CELL_GRASS) == 20.0
        assert _astar_cell_cost(CELL_TREE) == 40.0
        # 有路穿过的楼/水 (门洞、桥) 便宜穿; 实心楼/水贵穿
        assert _astar_cell_cost(CELL_BUILDING, on_road=True) == 20.0
        assert _astar_cell_cost(CELL_BUILDING, on_road=False) == 500.0
        assert _astar_cell_cost(CELL_WATER, on_road=True) == 20.0
        assert _astar_cell_cost(CELL_WATER, on_road=False) == 500.0

    def test_astar_prefers_road_over_grass_shortcut(self):
        """A* 宁可绕路也不横切草坪: 草地直穿更短, 但代价 20/格,
        绕路的路代价 1/格, 必须选绕路。"""
        # 10x6: 上下两条路, 中间是草坪; 起点左上, 终点右下。
        # 直穿草坪约 9 格 (代价 ~180); 沿路绕行约 16 格 (代价 ~16)。
        g = _grid("rrrrrrrrrr",
                  "r........r",
                  "r........r",
                  "r........r",
                  "r........r",
                  "rrrrrrrrrr")
        p = find_path_on_grid(g, (0, 0), (9, 5))
        assert p, "应找到路"
        # 路径上除起点/终点所在路格外, 不应进草地
        grass_cells = [(x, y) for x, y in p if g[y][x] == CELL_GRASS]
        assert grass_cells == [], f"A* 横切草坪: {grass_cells}"
        # 应沿着路走: 全部在路格上
        assert all(g[y][x] == CELL_ROAD for x, y in p)


class TestRoadProximityMask:
    def test_mask_covers_road_line(self):
        from baker.core.gridifier import _road_proximity_mask
        roads = [{"nodes": [(0.0, 0.5), (1.0, 0.5)], "highway_type": "residential"}]
        mask = _road_proximity_mask(roads, (0.0, 0.0, 1.0, 1.0), (10, 10), radius=1)
        # 路在 lat=0.5 -> y=5 行附近, 半径 1 -> y=4,5,6 行
        assert (5, 5) in mask
        assert (0, 5) in mask and (9, 5) in mask
        assert (5, 4) in mask and (5, 6) in mask
        assert (5, 0) not in mask and (5, 9) not in mask

    def test_empty_roads_empty_mask(self):
        from baker.core.gridifier import _road_proximity_mask
        assert _road_proximity_mask([], (0.0, 0.0, 1.0, 1.0), (10, 10)) == set()


class TestCarveRoutePassages:
    def test_carves_building_and_water(self):
        from baker.core.gridifier import carve_route_passages
        g = _grid("rrr",
                  "rBr",
                  "rwr")
        heights = [[0, 0, 0], [0, 3, 0], [0, 0, 0]]
        n = carve_route_passages(g, [{"x": 1, "y": 1}, {"x": 1, "y": 2}], heights)
        assert n == 2
        assert g[1][1] == CELL_ROAD and g[2][1] == CELL_ROAD
        assert heights[1][1] == 0  # 层数清零
        assert g[0][0] == CELL_ROAD  # 本来是路的格子不动 (不重复计)

    def test_carve_counts_only_blocked(self):
        from baker.core.gridifier import carve_route_passages
        g = _grid("rrr", "rrr", "rrr")
        assert carve_route_passages(g, [{"x": 0, "y": 0}, {"x": 1, "y": 1}]) == 0
        assert carve_route_passages(g, []) == 0


class TestRouteAlongRoads:
    def test_stays_on_passable_cells(self):
        # L 形路网 + 广场: 锚点有偏离路的, 寻到的路线全程可走
        g = _grid("..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  ".....p....r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........")
        bbox = (0.0, 0.0, 1.0, 1.0)  # min_lat, min_lng, max_lat, max_lng
        # 锚点 (lng, lat): (2,10) 路上 -> (5,5) 草地上偏离 -> (18,10) 路上
        # lng -> x = lng*20; lat -> y = (1-lat)*20
        pts = [(0.10, 0.50), (0.25, 0.75), (0.90, 0.50)]
        route = route_along_roads(pts, g, bbox, (20, 20))
        assert len(route) >= 2
        assert route[0] == {"x": 2, "y": 10}
        assert route[-1] == {"x": 18, "y": 10}
        for p in route:
            assert _route_cell_cost(g[p["y"]][p["x"]]) is not None, p
        # 间距约 2 格 (加密后; 斜步累计可到 ~3.4)
        for a, b in zip(route, route[1:]):
            import math
            assert math.hypot(b["x"] - a["x"], b["y"] - a["y"]) <= 3.5

    def test_empty_and_single(self):
        g = _grid("rrr", "rrr", "rrr")
        bbox = (0.0, 0.0, 1.0, 1.0)
        assert route_along_roads([], g, bbox, (3, 3)) == []
        # (lng=1/3, lat=2/3) -> fx=1.0, fy=1.0, 正好 (1,1)
        assert route_along_roads([(1.0 / 3, 2.0 / 3)], g, bbox, (3, 3)) == [{"x": 1, "y": 1}]

    def test_spine_x_pulls_displaced_anchors_to_axis(self):
        # 两条平行南北路: 主轴 x=10, 偏东的边路 x=16。锚点落在边路
        # 上 (老日志切片错位), 不传 spine 时路线就沿边路走; 传了
        # spine_x=10 后锚点横向收到主轴, 路线沿主轴走。
        rows = []
        for _y in range(20):
            row = list("." * 20)
            row[10] = "r"
            row[16] = "r"
            rows.append("".join(row))
        g = _grid(*rows)
        bbox = (0.0, 0.0, 1.0, 1.0)
        # 锚点 (lng, lat): x=16 列, y=18 (南) 与 y=2 (北)
        pts = [(0.80, 0.10), (0.80, 0.90)]
        plain = route_along_roads(pts, g, bbox, (20, 20))
        assert plain and all(p["x"] == 16 for p in plain), plain
        spined = route_along_roads(pts, g, bbox, (20, 20), spine_x=10)
        assert spined and all(p["x"] == 10 for p in spined), spined
        assert spined[0] == {"x": 10, "y": 18}
        assert spined[-1] == {"x": 10, "y": 2}

    def test_buildings_never_on_route(self):
        # 楼群挡路: 锚点连线横穿楼群, 寻路必须绕开
        g = _grid("rrrrrrrrrrrr",
                  "rBBBBBBBBBBr",
                  "rBBBBBBBBBBr",
                  "rBBBBBBBBBBr",
                  "rrrrrrrrrrrr")
        bbox = (0.0, 0.0, 1.0, 1.0)
        # 锚点在楼群上下两侧的路上
        pts = [(0.05, 0.9), (0.95, 0.9)]  # y=0 行? lat 0.9 -> y=(1-0.9)*5=0.5->0
        route = route_along_roads(pts, g, bbox, (12, 5))
        assert len(route) >= 2
        for p in route:
            assert g[p["y"]][p["x"]] != CELL_BUILDING, p
            assert g[p["y"]][p["x"]] != CELL_WATER, p

    def test_route_through_gate_with_osm_road(self):
        # 楼墙竖着切断整张图, 只有 y=5 处一道门 (OSM 路穿过):
        # 有路网掩码时寻路从门洞过, 刻通道后门洞变路, 路线采样全过
        from baker.core.gridifier import carve_route_passages
        rows = []
        for y in range(10):
            row = list("r" * 20) if y == 5 else list("." * 20)
            for x in (9, 10, 11):
                row[x] = "B"
            rows.append("".join(row))
        g = _grid(*rows)
        bbox = (0.0, 0.0, 1.0, 1.0)
        osm_roads = [{"nodes": [(0.0, 0.5), (1.0, 0.5)], "highway_type": "residential"}]
        pts = [(0.05, 0.5), (0.95, 0.5)]
        route = route_along_roads(pts, g, bbox, (20, 10), osm_roads=osm_roads)
        assert len(route) >= 2
        # 路线沿 y=5 走, 穿过门洞 (9,5),(10,5),(11,5)
        assert (9, 5) in [(p["x"], p["y"]) for p in route]
        assert (11, 5) in [(p["x"], p["y"]) for p in route]
        # 刻通道: 门洞 3 格变路
        n = carve_route_passages(g, route)
        assert n == 3
        for p in route:
            assert g[p["y"]][p["x"]] in (CELL_ROAD, CELL_PLAZA, CELL_SIDEWALK), p


class TestApplyPathOverlay:
    def test_overlay_draws_road(self):
        g = _grid(".....",
                  ".....",
                  ".....",
                  ".....",
                  ".....")
        apply_path_overlay(g, [{"x": 0, "y": 2}, {"x": 4, "y": 2}])
        assert g[2][1] == CELL_ROAD
        assert g[2][3] == CELL_ROAD
        assert g[0][0] == CELL_GRASS  # 线宽 3 盖 y=1..3, y=0 不动

    def test_overlay_empty_noop(self):
        g = _grid(".....", ".....")
        before = [row[:] for row in g]
        apply_path_overlay(g, [])
        assert g == before


class TestRouteAlongRoadsIntegration:
    """小 OSM -> 干净网格 -> 沿路网寻路 -> 验全程不进楼不进水。"""

    def test_osm_grid_route(self):
        els = []
        # 节点: 一条东西向路 (y=0.5), 南边一栋楼
        nodes = [(0.0, 0.5), (0.25, 0.5), (0.5, 0.5), (0.75, 0.5), (1.0, 0.5),
                 (0.4, 0.1), (0.6, 0.1), (0.6, 0.3), (0.4, 0.3)]
        for i, (lng, lat) in enumerate(nodes, start=1):
            els.append({"type": "node", "id": i, "lat": lat, "lon": lng})
        els.append({"type": "way", "id": 100, "nodes": [1, 2, 3, 4, 5],
                    "tags": {"highway": "residential"}})
        els.append({"type": "way", "id": 101, "nodes": [6, 7, 8, 9, 6],
                    "tags": {"building": "yes"}})
        parsed = parse_overpass({"elements": els})
        bbox = (0.0, 0.0, 1.0, 1.0)
        grid, _, _ = osm_to_grid(parsed, bbox, (20, 10))
        # 锚点沿路, 中间一个偏到楼里
        pts = [(0.05, 0.5), (0.5, 0.2), (0.95, 0.5)]
        route = route_along_roads(pts, grid, bbox, (20, 10))
        assert len(route) >= 2
        for p in route:
            v = grid[p["y"]][p["x"]]
            assert v != CELL_BUILDING, p
            assert v != CELL_WATER, p
        # 叠加后路线格子是路
        apply_path_overlay(grid, route)
        for p in route:
            assert grid[p["y"]][p["x"]] == CELL_ROAD


class TestWaterProximityMask:
    def test_mask_covers_water_line(self):
        from baker.core.gridifier import _water_proximity_mask
        water = [{"nodes": [(0.0, 0.5), (1.0, 0.5)], "type": "river"}]
        mask = _water_proximity_mask(water, (0.0, 0.0, 1.0, 1.0), (10, 10), radius=1)
        # 水线在 lat=0.5 -> y=5 行附近, 半径 1 -> y=4,5,6 行
        assert (5, 5) in mask
        assert (0, 5) in mask and (9, 5) in mask
        assert (5, 4) in mask and (5, 6) in mask
        assert (5, 0) not in mask and (5, 9) not in mask

    def test_empty_water_empty_mask(self):
        from baker.core.gridifier import _water_proximity_mask
        assert _water_proximity_mask([], (0.0, 0.0, 1.0, 1.0), (10, 10)) == set()
        assert _water_proximity_mask(None, (0.0, 0.0, 1.0, 1.0), (10, 10)) == set()


class TestFindPathWaterPenalty:
    def test_prefers_road_away_from_water(self):
        # 3 行宽的路 (y=4,5,6), 水线在 y=8: 贴水边的 y=6 行加价,
        # 路线应从 y=6 让到 y=5 (路 1+2=3 仍比草 4 便宜, 不离路去走草)
        from baker.core.gridifier import _water_proximity_mask
        g = _grid("....................",
                  "....................",
                  "....................",
                  "....................",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "....................",
                  "....................",
                  "....................")
        bbox = (0.0, 0.0, 1.0, 1.0)
        water = [{"nodes": [(0.0, 0.2), (1.0, 0.2)], "type": "river"}]
        wmask = _water_proximity_mask(water, bbox, (20, 10), radius=2)
        assert (6, 6) in wmask and (5, 5) not in wmask
        path = find_path_on_grid(g, (0, 6), (19, 6), water_mask=wmask)
        assert path[0] == (0, 6) and path[-1] == (19, 6)
        # 中间点都让到离水远的行 (y<=5), 不贴着水边走
        assert all(y <= 5 for _, y in path[1:-1]), path
        assert all(_route_cell_cost(g[y][x]) is not None for x, y in path)

    def test_bridge_crossing_still_works(self):
        # 竖河 (x=9,10 全高是水) + 横桥 (y=5 是路): 桥是唯一过河处,
        # 贴水加价也不能让路线绕开, 必须走桥过去, 且走桥心
        from baker.core.gridifier import _water_proximity_mask
        rows = []
        for y in range(10):
            row = ["."] * 20
            for x in range(20):
                row[x] = "r" if y == 5 else row[x]
            if y != 5:
                row[9] = "w"
                row[10] = "w"
            rows.append("".join(row))
        g = _grid(*rows)
        bbox = (0.0, 0.0, 1.0, 1.0)
        water = [{"nodes": [(0.475, 0.0), (0.475, 1.0)], "type": "river"}]
        wmask = _water_proximity_mask(water, bbox, (20, 10), radius=2)
        path = find_path_on_grid(g, (0, 5), (19, 5), water_mask=wmask)
        assert path[0] == (0, 5) and path[-1] == (19, 5)
        # 走桥过去, 不绕河端 (河贯通全高, 也绕不过去)
        assert (9, 5) in path and (10, 5) in path
        assert all(_route_cell_cost(g[y][x]) is not None for x, y in path)


class TestRouteAlongRoadsWater:
    def test_osm_water_shifts_route_off_water_edge(self):
        # route_along_roads 接 osm_water: 3 行宽的路 + 南边水线,
        # 加密后的路点中间段应让到离水远的行
        g = _grid("....................",
                  "....................",
                  "....................",
                  "....................",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "....................",
                  "....................",
                  "....................")
        bbox = (0.0, 0.0, 1.0, 1.0)
        water = [{"nodes": [(0.0, 0.2), (1.0, 0.2)], "type": "river"}]
        # 锚点 (lng, lat): y=6 行两端
        route = route_along_roads([(0.05, 0.4), (0.95, 0.4)], g, bbox, (20, 10),
                                  osm_water=water)
        assert len(route) >= 2
        assert route[0] == {"x": 1, "y": 6} and route[-1] == {"x": 19, "y": 6}
        assert all(p["y"] <= 5 for p in route[1:-1]), route


class TestSplitTransportAtGate:
    """split_transport_at_gate: 按城门分段交通工具 (baker/core/gridifier.py)

    道理: 开车只能到宫门口, 进宫城只能步行。分段点按 OSM 城门建筑
    的包围盒算, 不是写死坐标/点号。
    """

    def test_splits_at_gate_bbox(self):
        # 南北向路线 x=10, y 18->2 (向北); 城门包围盒 x 8-12, y 8-12。
        # 投影: fx=lng*20, fy=(1-lat)*20。城门节点 lng 0.4-0.6,
        # lat 0.4-0.6 -> fx 8-12, fy 8-12。
        gate = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]
        bbox = (0.0, 0.0, 1.0, 1.0)
        wps = [{"x": 10, "y": y} for y in (18, 16, 14, 12, 10, 8, 6, 4, 2)]
        out = split_transport_at_gate(wps, gate, bbox, (20, 20))
        # 第一次进包围盒是 y=12 (idx 3); 之前开车, 从那点起步行,
        # 出了包围盒往北 (y<8) 也还是步行
        assert [p["transport"] for p in out] == (
            ["driving"] * 3 + ["walking"] * 6), out
        assert [(p["x"], p["y"]) for p in out] == [(10, y) for y in (18, 16, 14, 12, 10, 8, 6, 4, 2)]

    def test_gate_moves_split_moves(self):
        # 城门换到 y 14-16 处, 分段点跟着动 (不是写死点号)
        gate = [(0.4, 0.3), (0.6, 0.3), (0.6, 0.2), (0.4, 0.2)]
        bbox = (0.0, 0.0, 1.0, 1.0)
        wps = [{"x": 10, "y": y} for y in (18, 16, 14, 12, 10, 8, 6, 4, 2)]
        out = split_transport_at_gate(wps, gate, bbox, (20, 20))
        # 城门 fy=(1-lat)*20: lat 0.2-0.3 -> fy 14-16, 第一次进是 y=16 (idx 1)
        assert [p["transport"] for p in out] == (
            ["driving"] * 1 + ["walking"] * 8), out

    def test_no_gate_crossing_all_outside(self):
        # 路线在 x=2, 根本不进城门包围盒 (x 8-12): 全段开车, 不硬切
        gate = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]
        bbox = (0.0, 0.0, 1.0, 1.0)
        wps = [{"x": 2, "y": y} for y in (18, 12, 6, 2)]
        out = split_transport_at_gate(wps, gate, bbox, (20, 20))
        assert [p["transport"] for p in out] == ["driving"] * 4, out

    def test_empty_and_no_gate(self):
        bbox = (0.0, 0.0, 1.0, 1.0)
        assert split_transport_at_gate([], [(0.4, 0.4)], bbox, (20, 20)) == []
        wps = [{"x": 10, "y": 18}, {"x": 10, "y": 2}]
        out = split_transport_at_gate(wps, [], bbox, (20, 20))
        assert [p["transport"] for p in out] == ["driving", "driving"]


class TestSmoothPathOnGrid:
    """smooth_path_on_grid: 贪心视线法平滑逐格路径 (Bug 1)

    道理: A* 出来的是逐格点列 (点距 1-2 格 = 楼梯/锯齿), 视线法从
    一点往前看、能直线通到的最远点就直连; 直线段穿楼/水就保留拐点。
    """

    def _staircase(self, n=10):
        # 斜向楼梯: (0,0),(1,1),(2,2),... 全是斜步, 平滑后应只剩两端
        return [{"x": i, "y": i} for i in range(n)]

    def test_diagonal_staircase_collapses_to_endpoints(self):
        g = _grid("rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr")
        out = smooth_path_on_grid(self._staircase(10), g)
        assert out == [{"x": 0, "y": 0}, {"x": 9, "y": 9}]

    def test_zigzag_on_open_ground_collapses(self):
        # 横平竖直锯齿: (0,0),(1,0),(1,1),(2,1),(2,2)... 全是 1 格步
        wps = []
        for i in range(6):
            wps.append({"x": i, "y": i})
            wps.append({"x": i + 1, "y": i})
        wps = [wps[0]] + [p for p in wps[1:] if p != wps[0]]
        g = _grid(*["r" * 12 for _ in range(12)])
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 0}
        assert out[-1] == wps[-1]
        assert len(out) <= 3  # 空地上直线可达, 最多剩一两个中间点

    def test_building_keeps_the_corner(self):
        # 楼墙横在中间, 只有 x=5 处留一个路口, 路线绕墙角走: 直线横切
        # 会穿楼, 拐点必须保留
        g = _grid("rrrrrrrrrr",
                  "rrrrrrrrrr",
                  "BBBBBrBBBB",
                  "rrrrrrrrrr",
                  "rrrrrrrrrr")
        # 绕路点列: 沿顶路向东, 在缺口 x=5 处南下, 再沿底路向东
        wps = [{"x": x, "y": 0} for x in range(6)]
        wps += [{"x": 5, "y": 1}, {"x": 5, "y": 2}, {"x": 5, "y": 3}]
        wps += [{"x": x, "y": 4} for x in range(6, 10)]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 0} and out[-1] == {"x": 9, "y": 4}
        # 每段直线都不穿楼 (用同一条校验函数复核)
        for a, b in zip(out, out[1:]):
            assert not _segment_crosses_blocked(g, a["x"], a["y"], b["x"], b["y"])
        # 拐点留下来了: 必须经过缺口列 x=5 附近, 不能直接从 (0,0) 连到 (9,4)
        assert len(out) > 2
        assert any(p["x"] == 5 for p in out)

    def test_water_keeps_the_corner(self):
        # 河横贯, 只有 x=2 处一座桥: 直线横切会穿水, 拐点必须保留
        g = _grid("rrrrrrrrrr",
                  "wwwwrwwwww",
                  "rrrrrrrrrr")
        wps = [{"x": x, "y": 0} for x in range(5)]
        wps += [{"x": 4, "y": 1}, {"x": 4, "y": 2}]
        wps += [{"x": x, "y": 2} for x in range(5, 10)]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 0} and out[-1] == {"x": 9, "y": 2}
        for a, b in zip(out, out[1:]):
            assert not _segment_crosses_blocked(g, a["x"], a["y"], b["x"], b["y"])
        assert len(out) > 2
        assert any(p["x"] == 4 for p in out)  # 必须经过桥

    def test_subset_endpoints_and_short(self):
        g = _grid("rrr", "rrr", "rrr")
        wps = [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 2}]
        out = smooth_path_on_grid(wps, g)
        assert out[0] in wps and out[-1] in wps
        assert all(p in wps for p in out)
        assert smooth_path_on_grid([], g) == []
        assert smooth_path_on_grid([{"x": 1, "y": 1}], g) == [{"x": 1, "y": 1}]
        two = [{"x": 0, "y": 0}, {"x": 2, "y": 2}]
        assert smooth_path_on_grid(two, g) == two

    def test_no_corner_cut(self):
        # 两栋楼斜对角相邻: 直线从楼角斜切过去要被挡住, 拐点保留
        g = _grid("rrB.",
                  "rBB.",
                  "rrrr")
        # 直线 (1,0)->(2,2) 会从 (2,1)/(1,1) 的楼角切过
        assert _segment_crosses_blocked(g, 1, 0, 2, 2)
        wps = [{"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 1, "y": 2}, {"x": 2, "y": 2}]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 1, "y": 0} and out[-1] == {"x": 2, "y": 2}
        for a, b in zip(out, out[1:]):
            assert not _segment_crosses_blocked(g, a["x"], a["y"], b["x"], b["y"])

    def test_smooths_real_astar_output(self):
        # 端到端: A* 在 L 形路网上的逐格输出, 平滑后点变少、每段变长、
        # 全程不穿楼/水
        g = _grid("..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "rrrrrrrrrrrrrrrrrrrr",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........",
                  "..........r.........")
        raw = find_path_on_grid(g, (0, 10), (10, 0))
        assert len(raw) == 20  # 逐格 A* 本来就很碎 (L 形: 横 11 格 + 竖 10 格 - 拐角重复 1)
        wps = [{"x": x, "y": y} for x, y in raw]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 10} and out[-1] == {"x": 10, "y": 0}
        assert len(out) < len(wps)
        # L 形的拐角 (10,10) 不能被抄近道切掉: 每段中点离 L 形路不超过 3 格
        import math as _math
        for a, b in zip(out, out[1:]):
            assert not _segment_crosses_blocked(g, a["x"], a["y"], b["x"], b["y"])
            assert g[b["y"]][b["x"]] != CELL_BUILDING
            assert g[b["y"]][b["x"]] != CELL_WATER
            mx, my = (a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2
            # 到 L 形路的距离 = 到横腿 (y=10, x 0..10) 与竖腿 (x=10, y 0..10) 的最小值
            d_h = min(_math.hypot(mx - x, my - 10) for x in range(11))
            d_v = min(_math.hypot(mx - 10, my - y) for y in range(11))
            d_to_L = min(d_h, d_v)
            assert d_to_L <= 3.5, (a, b, d_to_L)

    def test_grass_field_not_cut(self):
        # L 形路绕草坪: 直线抄近道会横切草地, 拐点必须保留、路线贴路走
        # (回归: 旧版 blocked 只拦楼/水, 直线切草坪也被当成可走)
        g = _grid("r.........",
                  "r.........",
                  "r.........",
                  "r.........",
                  "rrrrrrrrrr")
        # 沿 L 形路走: 左侧竖路南下, 再沿底路向东
        wps = [{"x": 0, "y": y} for y in range(5)]
        wps += [{"x": x, "y": 4} for x in range(1, 10)]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 0} and out[-1] == {"x": 9, "y": 4}
        # 直线 (0,0)->(9,4) 横切草坪, 必须被挡住
        assert _segment_crosses_blocked(g, 0, 0, 9, 4)
        # 拐角 (0,4) 必须留下来, 不能直接从起点连到终点
        assert any(p["x"] == 0 and p["y"] == 4 for p in out)
        assert len(out) > 2
        # 每段直线只走路/广场/人行道, 不进草/树/楼/水
        for a, b in zip(out, out[1:]):
            assert not _segment_crosses_blocked(g, a["x"], a["y"], b["x"], b["y"])

    def test_smoothed_stays_on_road_or_plaza(self):
        # 端到端: 带草坪/树/楼的路网, A* + 平滑后每段只走路/广场/人行道
        g = _grid("rrrrr.....",
                  "r...rrrrr.",
                  "r...r...r.",
                  "r...r.tt..",
                  "rrrrr...r.",
                  "....rrrrr.",
                  "....r.....",
                  "ppppprrrrr")
        # 从左上到右下: A* 会沿路走 (路 1, 广场 5, 草 20, 树 40, 优先贴路)
        raw = find_path_on_grid(g, (0, 0), (9, 7))
        assert raw, "A* 应该找得到路"
        wps = [{"x": x, "y": y} for x, y in raw]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 0} and out[-1] == {"x": 9, "y": 7}
        assert len(out) < len(wps)
        paved = {CELL_ROAD, CELL_PLAZA, CELL_SIDEWALK}
        for a, b in zip(out, out[1:]):
            assert not _segment_crosses_blocked(g, a["x"], a["y"], b["x"], b["y"])
            # 逐格复核: 每段直线上的每个格子都是铺装面
            for (x, y) in _straight_line_cells(a["x"], a["y"], b["x"], b["y"]):
                assert g[y][x] in paved, (a, b, x, y, g[y][x])


class TestRoadOverPlaza:
    """广场不跟路同价: A* 宁可绕路也不横切广场, 平滑不拉空地大斜线。

    回归: 广场是网格底色 (有 ground 数据时整图默认广场, 实测占 78%),
    广场代价跟路一样 (1.0) 时, A* 直接横切广场抄近道, 画出来的红线
    是横穿空地的大斜线、根本不贴灰色道路 (用户 2026-11-27 截图反馈)。
    修法: 广场代价 1.0 -> 5.0; 长平滑段必须大半走在真路上。
    """

    def test_astar_prefers_road_detour_over_plaza_cut(self):
        # U 形路绕着广场海: 起点左上、终点右上; 直线横切广场只有 12 格,
        # 绕 U 形路要 23 格。广场 5.0 时必须走 U 形路, 不能横切。
        g = _grid("r..........r",
                  "rppppppppppr",
                  "rppppppppppr",
                  "rppppppppppr",
                  "rppppppppppr",
                  "rppppppppppr",
                  "rrrrrrrrrrrr")
        path = find_path_on_grid(g, (0, 0), (11, 0))
        assert path, "A* 应该找得到路"
        assert path[0] == (0, 0) and path[-1] == (11, 0)
        # 全程走路格, 一个广场格都不踩 (广场 1.0 时会横切, 这个测试就挂)
        for (x, y) in path:
            assert g[y][x] == CELL_ROAD, (x, y, g[y][x])

    def test_plaza_crossable_when_no_road(self):
        # 没路可走时广场照样能穿 (宫里大院子、广场深处的 POI), 不能把路堵死
        g = _grid("pppppppppp",
                  "pppppppppp",
                  "pppppppppp")
        path = find_path_on_grid(g, (0, 0), (9, 2))
        assert path, "纯广场也得找得到路"
        assert path[0] == (0, 0) and path[-1] == (9, 2)
        for (x, y) in path:
            assert _route_cell_cost(g[y][x]) is not None

    def test_long_segment_mostly_off_road_blocked(self):
        # 长直线段大半不在真路上就判不可走 (横切广场的大斜线)
        g = _grid("rpppppppppp",
                  "rpppppppppp",
                  "rrrrrrrrrrp",
                  "ppppppppppr",
                  "ppppppppppr",
                  "ppppppppppr",
                  "rrrrrrrrrrr")
        # (0,0)->(9,2) 的直线切广场角: 10 格里只有一半是路, 必须挡住
        assert _segment_crosses_blocked(g, 0, 0, 9, 2)
        # 沿路走的段 (0,0)->(0,2) 全是路, 不挡
        assert not _segment_crosses_blocked(g, 0, 0, 0, 2)
        # 短段豁免: 5 格以内借道穿广场去接路, 不挡
        assert not _segment_crosses_blocked(g, 0, 0, 2, 1)

    def test_smoothed_line_mostly_on_road(self):
        # 端到端: 蜿蜒路穿过广场海, A* + 平滑后画出来的红线大半落在真路格上
        g = _grid("rpppppppppp",
                  "rpppppppppp",
                  "rrrrrrrrrrp",
                  "ppppppppppr",
                  "ppppppppppr",
                  "ppppppppppr",
                  "rrrrrrrrrrr")
        raw = find_path_on_grid(g, (0, 0), (10, 6))
        assert raw, "A* 应该找得到路"
        wps = [{"x": x, "y": y} for x, y in raw]
        out = smooth_path_on_grid(wps, g)
        assert out[0] == {"x": 0, "y": 0} and out[-1] == {"x": 10, "y": 6}
        # 画出来的红线 (各段 Bresenham 格子) 至少 60% 是真路格
        total = on_road = 0
        longest = 0
        for a, b in zip(out, out[1:]):
            cells = _straight_line_cells(a["x"], a["y"], b["x"], b["y"])
            longest = max(longest, len(cells))
            for (x, y) in cells:
                total += 1
                if g[y][x] in (CELL_ROAD, CELL_SIDEWALK):
                    on_road += 1
        assert total > 0 and on_road / total >= 0.6, (on_road, total)
        # 没有横穿空地的大斜线: 最长一段不超过 12 格
        assert longest <= 12, longest
