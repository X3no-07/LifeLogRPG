"""火红渲染器测试: baker/render/firered.py

覆盖:
- 模块能被 import, 默认网格 320x240
- 给一份小的合成网格 + OSM 输入能出一张图, 尺寸 = 网格 x 16px
- 图里楼 / 路 / 水 / 草都有像素 (不是全空白或全一种颜色)
- 没 OSM / 没 bbox 时降级只按网格画, 不报错
- 渲染失败不丢 JSON (BaseMode.write 照常写盘、返回 JSON 路径)
"""
from collections import Counter

import pytest

from baker.render import render_firered_map
from baker.config import load_config
from baker.core.schema import MapData
from baker.modes.base import BaseMode

# 小网格 40x30 (图 640x480), 够覆盖楼/路/水/草/树
W, H = 40, 30


def _grid():
    g = [[0] * W for _ in range(H)]
    # 一条横路 y=15
    for x in range(W):
        g[15][x] = 1
    # 一栋 8x6 的楼 (x=5..12, y=5..10)
    for y in range(5, 11):
        for x in range(5, 13):
            g[y][x] = 2
    # 一条竖河 x=30..31
    for y in range(H):
        g[y][30] = 3
        g[y][31] = 3
    # 几棵树
    for (x, y) in ((20, 5), (21, 5), (20, 6), (35, 25)):
        g[y][x] = 4
    return g


def _heights(grid):
    return [[2 if c == 2 else 0 for c in row] for row in grid]


def _path():
    return [{"x": x, "y": 15, "transport": "walking"} for x in range(2, 38, 2)]


def _osm():
    # bbox (min_lat, min_lng, max_lat, max_lng), 节点 (lng, lat)
    return {
        "roads": [
            {"highway_type": "residential",
             "nodes": [(0.0, 0.0), (0.01, 0.0), (0.02, 0.0)]},
            {"highway_type": "tertiary",
             "nodes": [(0.005, -0.005), (0.005, 0.005)]},
        ],
        "buildings": [
            {"nodes": [(0.001, 0.001), (0.004, 0.001), (0.004, 0.003),
                       (0.001, 0.003), (0.001, 0.001)],
             "levels": 2, "name": "测试楼"},
        ],
        "water": [
            {"nodes": [(0.015, -0.005), (0.015, 0.005)]},
        ],
        "green": [],
        "ground": [
            {"kind": "grass",
             "nodes": [(0.0, 0.002), (0.01, 0.002), (0.01, 0.004),
                       (0.0, 0.004), (0.0, 0.002)]},
        ],
    }


BBOX = (-0.005, 0.0, 0.005, 0.02)


def _count_colors(img):
    return Counter(img.getdata())


def test_import_and_default_grid_320x240():
    cfg = load_config()
    assert cfg["bake"]["viewport_grid_w"] == 320
    assert cfg["bake"]["viewport_grid_h"] == 240
    assert MapData().width == 320
    assert MapData().height == 240


def test_render_small_grid_size():
    img = render_firered_map(_grid(), _heights(_grid()), _path())
    assert img.size == (W * 16, H * 16)
    assert img.mode == "RGB"


def test_render_has_building_road_water_grass_pixels():
    img = render_firered_map(_grid(), _heights(_grid()), _path(),
                             osm=_osm(), bbox=BBOX)
    colors = _count_colors(img)
    # 图不是全空白 / 全一种颜色
    assert len(colors) > 20
    # 水蓝 (56,118,214) 存在
    assert colors.get((56, 118, 214), 0) > 100
    # 草绿 (110,190,70) 存在 (地面 / 树下)
    assert colors.get((110, 190, 70), 0) > 100
    # 路灰 (126,126,112) 存在
    assert colors.get((126, 126, 112), 0) > 100
    # 屋顶红系存在 (矢量楼 198,86,48 或瓦片屋顶)
    assert colors.get((198, 86, 48), 0) > 50
    # 路线红线 (220,40,40) 存在
    assert colors.get((220, 40, 40), 0) > 20


def test_render_without_osm_still_works():
    img = render_firered_map(_grid(), _heights(_grid()), _path())
    colors = _count_colors(img)
    assert len(colors) > 20
    assert colors.get((56, 118, 214), 0) > 100  # 网格水格兜底成水面
    assert colors.get((198, 86, 48), 0) > 50


def test_render_empty_grid_raises():
    with pytest.raises(ValueError):
        render_firered_map([])


def test_render_route_keeps_the_bend_in_the_saved_waypoints():
    # A clear road permits a diagonal shortcut, but playback takes this bend.
    img = render_firered_map([[1] * 8 for _ in range(8)], path=[(2, 2), (4, 2), (4, 4)])
    red = (220, 40, 40)
    assert img.getpixel((56, 40)) == red
    assert img.getpixel((72, 56)) == red
    assert img.getpixel((56, 56)) != red


def test_render_driving_points_do_not_draw_teleport_line():
    # driving 点是跳点: 红线只画 walking 段, 不能出现横跨地图的斜线。
    # 构造一条先 walking 后 driving 跳到对角的路径, 检查红线像素
    # 只出现在 walking 段附近 (y=15 附近), 不出现在对角连线上。
    path = ([{"x": x, "y": 15, "transport": "walking"} for x in range(2, 10)]
            + [{"x": 35, "y": 25, "transport": "driving"}])
    img = render_firered_map(_grid(), _heights(_grid()), path)
    route = (220, 40, 40)
    px = img.load()
    # 对角连线中点附近 (约 x=20,y=20 格 -> 像素 320,320) 不应有红线
    found = 0
    for dx in range(-8, 9):
        for dy in range(-8, 9):
            if px[320 + dx, 320 + dy] == route:
                found += 1
    assert found == 0
    # walking 段上有红线
    assert px[5 * 16 + 8, 15 * 16 + 8] == route


def test_render_failure_does_not_lose_json(tmp_path, monkeypatch):
    """渲染挂了, write() 仍要写出 JSON。"""
    import baker.modes.base as base_mod

    class _Mode(BaseMode):
        def run(self):
            p = self.payload
            p.map.grid = _grid()
            p.map.building_heights = _heights(p.map.grid)
            from baker.core.schema import Waypoint
            p.path = [Waypoint(x=x, y=15, t=float(x)) for x in range(2, 10)]
            self._render_ctx = {"bbox": BBOX, "osm": _osm(),
                                "start_name": "甲", "end_name": "乙"}
            return p

    mode = _Mode("test_render_fail", config=load_config())
    monkeypatch.setattr(base_mod, "get_output_dir", lambda cfg: tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("boom")

    import baker.render as render_mod
    monkeypatch.setattr(render_mod, "render_firered_map", _boom)
    mode.run()
    out = mode.write()
    assert out.exists()
    assert out.suffix == ".json"
    assert not (tmp_path / "test_render_fail_map.png").exists()
