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
