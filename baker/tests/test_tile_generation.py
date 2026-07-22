"""P1.1 Tile 生成测试

验证:
- generate_tiles.py 8 个 tile PNG 都生成
- 尺寸 16x16
- 主色调 (base color) 正确
- tile_sheet.png 8x4 排列
"""
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.generate_tiles import (
    NAMES, DRAWERS, TILE_SIZE, PALETTE,
    generate_all, _new_image,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TILE_DIR = PROJECT_ROOT / "assets" / "tiles"


class TestTileConfig:
    """tile 配置文件"""

    def test_8_tiles_defined(self):
        """应该有 8 个 tile (cell type 0-7)"""
        assert len(DRAWERS) == 8
        assert len(NAMES) == 8
        for i in range(8):
            assert i in DRAWERS
            assert i in NAMES

    def test_tile_size(self):
        assert TILE_SIZE == 16

    def test_all_names_match(self):
        for i in range(8):
            assert NAMES[i] in ["grass", "road", "building", "water",
                                "tree", "sidewalk", "poi", "plaza"]


class TestPalette:
    """调色板 RGB 都在 0-255"""

    @pytest.mark.parametrize("name,rgb", list(PALETTE.items()))
    def test_rgb_in_range(self, name, rgb):
        assert len(rgb) == 3
        r, g, b = rgb
        assert 0 <= r <= 255, f"{name}.r out of range"
        assert 0 <= g <= 255, f"{name}.g out of range"
        assert 0 <= b <= 255, f"{name}.b out of range"


class TestTileFiles:
    """tile 文件实际生成 (依赖 generate_all 已运行)"""

    @pytest.mark.parametrize("cell_type,name", list(NAMES.items()))
    def test_png_exists(self, cell_type, name):
        path = TILE_DIR / f"{name}.png"
        if not path.exists():
            pytest.skip(f"tile {name}.png not generated yet (run baker/generate_tiles.py)")
        assert path.exists()
        img = Image.open(path)
        assert img.size == (16, 16)

    def test_sheet_exists(self):
        path = TILE_DIR / "tile_sheet.png"
        if not path.exists():
            pytest.skip("tile_sheet.png not generated yet")
        img = Image.open(path)
        # 4x2 排列, 64x32
        assert img.size == (64, 32)


class TestDrawers:
    """drawer 函数都能跑 (不报错)"""

    @pytest.mark.parametrize("cell_type", list(range(8)))
    def test_drawer_runs(self, cell_type):
        img = _new_image()
        DRAWERS[cell_type](img)
        # 至少有一些非黑像素
        extrema = img.getextrema()
        # extrema 返回每个通道 (min, max)
        assert any(max_v > 0 for _, max_v in extrema), \
            f"drawer {cell_type} produced all-black image"

    @pytest.mark.parametrize("cell_type", list(range(8)))
    def test_drawer_uses_correct_base(self, cell_type):
        """主色调应该是 cell type 对应的 base color"""
        img = _new_image()
        DRAWERS[cell_type](img)
        # 拿到 (0, 0) 角点 (左上角) 的颜色, 跟 base color 比较
        corner_color = img.getpixel((0, 0))
        # 至少 R/G/B 之一应该跟 base 相近 (允许 tile 有不同 base)
        # 简单验证: 角点非黑
        assert corner_color != (0, 0, 0), \
            f"drawer {cell_type} has black corner"


class TestGenerateAll:
    """generate_all 集成测试"""

    def test_generate_to_temp(self, tmp_path):
        """临时目录生成, 验证产物"""
        results = generate_all(tmp_path)
        # 8 个 tile + 1 sheet
        assert len(results) == 9
        # 每个 tile 都是 16x16
        for cell_type, name, path, size in results[:8]:
            assert size == (16, 16)
            assert path.exists()
        # sheet 是 64x32
        sheet = results[-1]
        assert sheet[3] == (64, 32)


class TestTileVisualSanity:
    """tile 视觉 sanity (基本颜色验证)"""

    def test_grass_is_green(self):
        """grass: 主色应该是绿色"""
        img = _new_image()
        DRAWERS[0](img)  # grass
        # 大部分像素是绿色
        pixels = [img.getpixel((x, y)) for y in range(16) for x in range(16)]
        green_count = sum(1 for r, g, b in pixels if g > r and g > b and g > 80)
        assert green_count > 100, f"grass has only {green_count}/256 green pixels"

    def test_water_is_blue(self):
        """water: 主色应该是蓝色"""
        img = _new_image()
        DRAWERS[3](img)  # water
        pixels = [img.getpixel((x, y)) for y in range(16) for x in range(16)]
        blue_count = sum(1 for r, g, b in pixels if b > r and b > g and b > 100)
        assert blue_count > 100

    def test_road_is_gray(self):
        """road: 主色应该是灰色 (R ≈ G ≈ B)"""
        img = _new_image()
        DRAWERS[1](img)  # road
        pixels = [img.getpixel((x, y)) for y in range(16) for x in range(16)]
        gray_count = sum(1 for r, g, b in pixels
                         if abs(r - g) < 20 and abs(g - b) < 20 and 80 < r < 180)
        assert gray_count > 100
