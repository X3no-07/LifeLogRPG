"""Godot 播放器用渲染图当底图的约定测试 (P1.4)。

Godot 端 (scripts/world.gd) 依赖 baker 的两个约定, 在这里锁死:
1. write() 在 JSON 旁边出一张同名 _map.png, 尺寸 = 网格 x 16px/格
   (跟 tile_size 一致, Godot 里 Sprite2D 不用缩放就能跟路线坐标重合)。
2. GDScript 接线存在: loader.gd 派生 _map.png 路径, world.gd 优先加载
   渲染图、没有图才回退 TileMap, 有图时不重复画路线/POI/抬高块。
   (第 2 组是静态检查: 只读 GDScript 文本不断言行为, 防误删接线;
   真机渲染用 Godot 实跑截图核对, 见汇报。)
"""
from pathlib import Path

import pytest

from baker.config import load_config
from baker.core.schema import Waypoint
from baker.modes.base import BaseMode
from baker.render import render_firered_map

REPO = Path(__file__).resolve().parents[2]

# 小网格 40x30, 图应为 640x480
W, H = 40, 30


def _grid():
    g = [[0] * W for _ in range(H)]
    for x in range(W):
        g[15][x] = 1  # 横路
    for y in range(5, 11):
        for x in range(5, 13):
            g[y][x] = 2  # 楼
    return g


def test_render_map_png_next_to_json_and_16px_per_cell(tmp_path, monkeypatch):
    """write() 出图: 跟 JSON 同目录同名 _map.png, 尺寸 = 网格 x tile_size。"""
    import baker.modes.base as base_mod

    class _Mode(BaseMode):
        def run(self):
            p = self.payload
            p.map.grid = _grid()
            p.map.width = W
            p.map.height = H
            p.map.building_heights = [[2 if c == 2 else 0 for c in row]
                                      for row in p.map.grid]
            p.path = [Waypoint(x=x, y=15, t=float(x)) for x in range(2, 10)]
            self._render_ctx = {"bbox": None, "osm": None,
                                "start_name": "甲", "end_name": "乙"}
            return p

    mode = _Mode("test_godot_map", config=load_config())
    monkeypatch.setattr(base_mod, "get_output_dir", lambda cfg: tmp_path)
    mode.run()
    out = mode.write()
    assert out.exists()
    assert out.name == "test_godot_map.json"
    png = tmp_path / "test_godot_map_map.png"
    assert png.exists(), "渲染图应跟 JSON 同名 _map.png, 在同一目录"
    from PIL import Image
    with Image.open(png) as im:
        assert im.size == (W * 16, H * 16)
        assert im.size == (W * load_config()["bake"]["tile_size_px"],
                           H * load_config()["bake"]["tile_size_px"])


def test_render_firered_map_size_is_grid_times_16():
    img = render_firered_map(_grid())
    assert img.size == (W * 16, H * 16)


def _read_gd(name):
    return (REPO / "scripts" / name).read_text(encoding="utf-8")


def test_loader_exposes_map_image_path():
    src = _read_gd("loader.gd")
    assert "func get_map_image_path" in src
    assert "_map.png" in src
    assert 'ends_with(".json")' in src


def test_world_loads_rendered_map_with_tilemap_fallback():
    src = _read_gd("world.gd")
    # 加载分支存在 (FileAccess + PNG 解码 + Sprite2D)
    assert "func _load_rendered_map" in src
    assert "load_png_from_buffer" in src
    assert "RenderedMap" in src
    assert "Sprite2D" in src
    # 没图回退 TileMap
    assert "无渲染图, 用 TileMap" in src
    assert "TileMap set %d cells" in src
    # 有图时不重复画: 路线 / POI / 抬高块都只在没图时画
    assert "if map_tex == null:" in src
    assert "if loader.get_pois().size() > 0 and map_tex == null:" in src
    assert ("if loader.get_building_heights().size() > 0 and map_tex == null:"
            in src)
    # 换乘 pin 和室内 icon 图里没有, 两种模式都画 (不带 map_tex 守卫)
    assert "if loader.get_transit_markers().size() > 0:" in src
    assert "if loader.get_interiors().size() > 0:" in src


def test_mock_mode_renders_map_next_to_json(tmp_path, monkeypatch):
    """Mock 模式也要出图: 之前 run() 没填 _render_ctx, write() 不出图,
    Godot 跑 Mock 只能回退 TileMap 色块。Mock 没真实 OSM/bbox,
    只按网格画 (渲染器 osm/bbox 为空时降级, 不报错)。"""
    import baker.modes.base as base_mod
    from baker.modes import MockMode

    mode = MockMode("test_mock_map", config=load_config())
    monkeypatch.setattr(base_mod, "get_output_dir", lambda cfg: tmp_path)
    mode.run()
    out = mode.write()
    assert out.exists()
    assert out.name == "test_mock_map.json"
    png = tmp_path / "test_mock_map_map.png"
    assert png.exists(), "Mock 也应在 JSON 旁边出 _map.png, 否则 Godot 回退色块"
    from PIL import Image
    with Image.open(png) as im:
        assert im.size == (320 * 16, 240 * 16)


def test_mock_mode_constant_speed():
    """Mock 路径点时间戳按累计路程分 (匀速走): 之前每点固定 1.5s,
    5 格段 53 px/s、10 格段 107 px/s, 人物忽快忽慢 (抖动)。
    跟 text.py 同一个约定: 60 px/s 匀速, 每段速度相等。"""
    import math

    from baker.modes import MockMode

    mode = MockMode("test_mock_speed", config=load_config())
    payload = mode.run()
    speeds = []
    for a, b in zip(payload.path, payload.path[1:]):
        dt = b.t - a.t
        assert dt > 0, "时间戳必须单调递增"
        dist = math.hypot(b.x - a.x, b.y - a.y) * 16
        speeds.append(dist / dt)
    assert speeds, "Mock 路径不能为空"
    assert max(speeds) - min(speeds) < 0.01, (
        f"每段速度应相等, 实测 min={min(speeds):.1f} max={max(speeds):.1f}")
    assert abs(speeds[0] - 60.0) < 0.01, "应按 bake 默认步行速度 60 px/s 走"
    # 总时长约 29.3s (110 格 x 16px / 60), 对白 (4/12/18/28s) 都在总时长内
    assert abs(payload.path[-1].t - 110 * 16 / 60.0) < 0.01


def test_main_camera_clamped_and_no_smoothing():
    """Godot 相机: 直接跟随人物 + 夹到地图边界内, 不用位置平滑。
    平滑会让相机滞后人物 (滞后 = 速度/平滑速度), 速度一变、拐弯、
    换乘停顿时滞后量跟着变, 人物在画面里来回晃; 夹紧则是修地图
    边缘露出深色底 (视口伸出地图外)。"""
    src = _read_gd("main.gd")
    # 没有位置平滑 (lag 来源)
    assert "position_smoothing_enabled" not in src
    assert "position_smoothing_speed" not in src
    # 有夹紧函数, 跟随和初始化都走夹紧
    assert "func _clamp_camera_position" in src
    assert "camera.position = _clamp_camera_position(player.position)" in src
    # 夹紧逻辑: 可见世界尺寸 = 视口 / zoom, 地图尺寸 = 网格 x tile_size,
    # 地图比视口小时居中
    assert "get_visible_rect().size / camera.zoom" in src
    assert "get_grid_width() * tile_size" in src
    assert "get_grid_height() * tile_size" in src
    assert "map_px.x * 0.5" in src
    assert "clamp(pos.x, half.x, map_px.x - half.x)" in src
    assert "clamp(pos.y, half.y, map_px.y - half.y)" in src
