"""P1.1: 程序化生成 GBA 风格 16x16 tile PNG

8 个 cell type 各 1 个 tile (后续可加 variants):
  0 grass    1 road    2 building  3 water
  4 tree     5 sidewalk  6 poi      7 plaza

设计:
- 16x16 px (跟当前 tile_size 对齐)
- 4-6 色调色板 (GBA 限制)
- 像素艺术 (1x1 笔触, 无抗锯齿)
- 用 PIL Image.new() + ImageDraw.point() 画
- 输出到 assets/tiles/{name}.png (供 Godot TileSet 加载)

运行: python baker/generate_tiles.py
"""
import random
from pathlib import Path
from PIL import Image, ImageDraw

# 调色板 (跟 world.gd 的 PALETTE 对齐)
PALETTE = {
    "grass_base":   (77, 140, 71),
    "grass_dark":   (50, 100, 50),
    "grass_light":  (110, 180, 100),
    "road_base":    (107, 107, 115),
    "road_dark":    (71, 71, 77),
    "road_line":    (220, 200, 100),  # 黄虚线
    "road_light":   (140, 140, 145),
    "building_base":(140, 107, 77),
    "building_dark":(110, 80, 50),
    "building_roof":(80, 50, 30),
    "building_win": (200, 170, 130),
    "building_door":(50, 30, 20),
    "water_base":   (51, 102, 179),
    "water_light":  (90, 150, 220),
    "water_wave":   (140, 190, 240),
    "tree_trunk":   (90, 60, 30),
    "tree_leaves":  (26, 102, 38),
    "tree_leaf_lt": (60, 140, 80),
    "tree_grass":   (77, 140, 71),     # tree 底色 = grass (能种在草地上)
    "sidewalk_base":(200, 200, 200),
    "sidewalk_dark":(180, 180, 180),
    "poi_base":     (255, 220, 100),
    "poi_star":     (255, 255, 255),
    "poi_dark":     (200, 160, 50),
    "plaza_base":   (220, 200, 150),
    "plaza_dark":   (200, 180, 130),
    "plaza_light":  (235, 220, 180),
}

TILE_SIZE = 16

# 固定种子, 保证生成确定性
SEED = 42


def _new_image() -> Image.Image:
    return Image.new("RGB", (TILE_SIZE, TILE_SIZE))


def _put(img: Image.Image, x: int, y: int, color: tuple) -> None:
    """set single pixel (clamp)"""
    if 0 <= x < TILE_SIZE and 0 <= y < TILE_SIZE:
        img.putpixel((x, y), color)


def _fill(img: Image.Image, color: tuple) -> None:
    """fill entire image"""
    for y in range(TILE_SIZE):
        for x in range(TILE_SIZE):
            img.putpixel((x, y), color)


def _draw_grass(img: Image.Image) -> None:
    """grass: 绿底 + 几个稀疏草叶"""
    p = PALETTE
    _fill(img, p["grass_base"])
    rng = random.Random(SEED)
    # 4-6 个草叶点 (少一点, 避免视觉噪声)
    for _ in range(rng.randint(4, 6)):
        x, y = rng.randint(0, TILE_SIZE - 1), rng.randint(0, TILE_SIZE - 1)
        c = p["grass_dark"] if rng.random() < 0.5 else p["grass_light"]
        _put(img, x, y, c)


def _draw_road(img: Image.Image) -> None:
    """road: 灰底 + 简单边线 + 稀疏黄虚线
    实际游戏中需要 4 个方向变体, MVP 先 1 个
    """
    p = PALETTE
    _fill(img, p["road_base"])
    # 上下边 1px 深色 (暗示 "路肩")
    for x in range(TILE_SIZE):
        _put(img, x, 0, p["road_dark"])
        _put(img, x, TILE_SIZE - 1, p["road_dark"])
    # 中心黄虚线 (稀疏: 每 4px 画 1 个 dot, 避免密恐)
    for x in range(2, TILE_SIZE - 2, 4):
        _put(img, x, 7, p["road_line"])
        _put(img, x, 8, p["road_line"])
    # 一些噪声 (沥青)
    rng = random.Random(SEED + 1)
    for _ in range(2):
        x, y = rng.randint(1, TILE_SIZE - 2), rng.randint(2, 5)
        _put(img, x, y, p["road_light"])


def _draw_building(img: Image.Image) -> None:
    """building: 棕底 + 屋顶 + 窗户 + 门"""
    p = PALETTE
    _fill(img, p["building_base"])
    # 屋顶 (顶 3 行, 深棕)
    for y in range(0, 3):
        for x in range(TILE_SIZE):
            _put(img, x, y, p["building_roof"])
    # 墙身窗户 (3x3 在 2 边, 2 个)
    # 左窗
    for dy in range(3):
        for dx in range(3):
            _put(img, 2 + dx, 6 + dy, p["building_win"])
    # 右窗
    for dy in range(3):
        for dx in range(3):
            _put(img, 10 + dx, 6 + dy, p["building_win"])
    # 门 (底中央, 2x3 深色)
    for dy in range(3):
        for dx in range(2):
            _put(img, 7 + dx, 12 + dy, p["building_door"])
    # 屋顶瓦片细节
    for x in range(0, TILE_SIZE, 2):
        _put(img, x, 2, p["building_dark"])


def _draw_water(img: Image.Image) -> None:
    """water: 蓝底 + 浅蓝波浪"""
    p = PALETTE
    _fill(img, p["water_base"])
    # 2 条波浪 (横向, 错开 1px 起伏)
    for y_offset in (4, 10):
        for x in range(TILE_SIZE):
            y = y_offset + (1 if (x // 2) % 2 == 0 else 0)
            if 0 <= y < TILE_SIZE:
                _put(img, x, y, p["water_light"])
    # 几个高光点
    rng = random.Random(SEED + 3)
    for _ in range(2):
        x, y = rng.randint(0, TILE_SIZE - 1), rng.randint(0, TILE_SIZE - 1)
        _put(img, x, y, p["water_wave"])


def _draw_tree(img: Image.Image) -> None:
    """tree: 草地底 + 树干 + 树冠
    注意: tree 实际显示在 grid 上是单格, 不是覆盖整 tile
    实际 P0 实现是 tree 颜色 = 26,102,38 单点
    这里画一个 mini 树: 草地 + 中心圆 + 树干
    """
    p = PALETTE
    _fill(img, p["tree_grass"])
    # 树干 (中央 2x3 棕)
    for dy in range(3):
        for dx in range(2):
            _put(img, 7 + dx, 9 + dy, p["tree_trunk"])
    # 树冠 (3x3 圆, 中心)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy <= 5:  # 近似圆
                c = p["tree_leaves"] if (dx + dy) % 2 == 0 else p["tree_leaf_lt"]
                _put(img, 8 + dx, 6 + dy, c)
    # 1-2 个高光
    rng = random.Random(SEED + 4)
    for _ in range(2):
        x = 8 + rng.randint(-1, 1)
        y = 6 + rng.randint(-1, 1)
        if 0 <= x < TILE_SIZE and 0 <= y < TILE_SIZE:
            _put(img, x, y, p["tree_leaf_lt"])


def _draw_sidewalk(img: Image.Image) -> None:
    """sidewalk: 浅灰底 + 1px 暗线 (4x4 砖块 pattern)"""
    p = PALETTE
    _fill(img, p["sidewalk_base"])
    # 水平线 y=4, y=11
    for y in (4, 11):
        for x in range(TILE_SIZE):
            _put(img, x, y, p["sidewalk_dark"])
    # 垂直线 x=4, x=8, x=12 (跟水平线交叉, 形成砖块)
    for y in range(TILE_SIZE):
        if y == 4 or y == 11:
            continue
        for x in (4, 8, 12):
            _put(img, x, y, p["sidewalk_dark"])


def _draw_poi(img: Image.Image) -> None:
    """poi: 金底 + 中心白星 (作为 POI marker 的备用 tile)"""
    p = PALETTE
    _fill(img, p["poi_base"])
    # 中心白点
    _put(img, 7, 7, p["poi_star"])
    _put(img, 8, 7, p["poi_star"])
    _put(img, 7, 8, p["poi_star"])
    _put(img, 8, 8, p["poi_star"])
    # 边框 (深金)
    for x in range(TILE_SIZE):
        _put(img, x, 0, p["poi_dark"])
        _put(img, x, TILE_SIZE - 1, p["poi_dark"])
    for y in range(TILE_SIZE):
        _put(img, 0, y, p["poi_dark"])
        _put(img, TILE_SIZE - 1, y, p["poi_dark"])


def _draw_plaza(img: Image.Image) -> None:
    """plaza: 米色底 + 棋盘格 pattern (4x4 砖)"""
    p = PALETTE
    for y in range(TILE_SIZE):
        for x in range(TILE_SIZE):
            if (x // 4 + y // 4) % 2 == 0:
                _put(img, x, y, p["plaza_base"])
            else:
                _put(img, x, y, p["plaza_dark"])


# cell type -> drawer
DRAWERS = {
    0: _draw_grass,
    1: _draw_road,
    2: _draw_building,
    3: _draw_water,
    4: _draw_tree,
    5: _draw_sidewalk,
    6: _draw_poi,
    7: _draw_plaza,
}

# cell type -> file name
NAMES = {
    0: "grass",
    1: "road",
    2: "building",
    3: "water",
    4: "tree",
    5: "sidewalk",
    6: "poi",
    7: "plaza",
}


def generate_all(out_dir: Path) -> list:
    """生成所有 tile, 返回 [(type, path, size), ...]
    同时生成 tile_sheet.png (4x2 拼接, 64x32) 供 Godot TileSet 单 texture 加载
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for cell_type, drawer in DRAWERS.items():
        img = _new_image()
        drawer(img)
        name = NAMES[cell_type]
        path = out_dir / f"{name}.png"
        img.save(path)
        results.append((cell_type, name, path, img.size))
        print(f"  [tile] type={cell_type} {name}.png  size={img.size}")

    # 拼 4x2 sheet (64x32)
    sheet_w = TILE_SIZE * 4   # 64
    sheet_h = TILE_SIZE * 2   # 32
    sheet = Image.new("RGB", (sheet_w, sheet_h), (38, 51, 77))  # 用 sky 色填充
    for i, (cell_type, name, _, _) in enumerate(results):
        col = i % 4
        row = i // 4
        tile = Image.open(out_dir / f"{name}.png")
        sheet.paste(tile, (col * TILE_SIZE, row * TILE_SIZE))
    sheet_path = out_dir / "tile_sheet.png"
    sheet.save(sheet_path)
    print(f"  [tile] sheet: tile_sheet.png  size={sheet.size}")
    results.append((-1, "sheet", sheet_path, sheet.size))
    return results


if __name__ == "__main__":
    # 默认输出到 assets/tiles/
    project_root = Path(__file__).resolve().parent.parent
    out = project_root / "assets" / "tiles"
    print(f"[generate_tiles] 输出: {out}")
    results = generate_all(out)
    print(f"[generate_tiles] 完成: {len(results) - 1} 个 tile + 1 sheet")
