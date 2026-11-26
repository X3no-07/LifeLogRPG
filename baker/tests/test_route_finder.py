"""沿路网寻路测试: 锚点吸附 + A* 沿路走 + 加密 (baker 源代码改动, 不针对某一座城)

覆盖 (baker/core/gridifier.py 新增):
- _route_cell_cost: 路/广场/人行道 1, 草 4, 树 8, 楼/水/POI 不可走
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
    route_along_roads, apply_path_overlay,
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
        assert _route_cell_cost(CELL_PLAZA) == 1.0
        assert _route_cell_cost(CELL_SIDEWALK) == 1.0
        assert _route_cell_cost(CELL_GRASS) == 4.0
        assert _route_cell_cost(CELL_TREE) == 8.0
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
        assert _astar_cell_cost(CELL_GRASS) == 4.0
        assert _astar_cell_cost(CELL_TREE) == 8.0
        # 有路穿过的楼/水 (门洞、桥) 便宜穿; 实心楼/水贵穿
        assert _astar_cell_cost(CELL_BUILDING, on_road=True) == 20.0
        assert _astar_cell_cost(CELL_BUILDING, on_road=False) == 500.0
        assert _astar_cell_cost(CELL_WATER, on_road=True) == 20.0
        assert _astar_cell_cost(CELL_WATER, on_road=False) == 500.0


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
