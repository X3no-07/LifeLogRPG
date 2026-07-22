#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grid 预览图工具
读 saved_logs/log_*.json, 把 map.grid + path + pois 渲染成 PNG

P1.1: 优先用真实 tile (assets/tiles/{name}.png), fallback 到 PALETTE 纯色
"""
import sys
import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 备用调色板 (没有 tile 时用)
PALETTE = {
    0: (123, 180, 113),
    1: (107, 107, 115),
    2: (140, 107, 77),
    3: (51, 102, 179),
    4: (26, 102, 38),
    5: (200, 200, 200),
    6: (255, 220, 100),
    7: (220, 200, 150),
}

# 加载 tile (P1.1)
TILE_DIR = PROJECT_ROOT / "assets" / "tiles"
TILE_NAMES = {0: "grass", 1: "road", 2: "building", 3: "water",
              4: "tree", 5: "sidewalk", 6: "poi", 7: "plaza"}

# P1.3 室内 icon
INTERIOR_CATS = ["cafe", "restaurant", "shop", "office", "hotel", "hospital",
                 "bank", "school", "museum", "pharmacy", "library", "fitness",
                 "theater"]


def _load_tiles() -> dict:
    """加载所有 tile PNG, 返回 {cell_type: Image}"""
    tiles = {}
    for ct, name in TILE_NAMES.items():
        path = TILE_DIR / f"{name}.png"
        if path.exists():
            tiles[ct] = Image.open(path).convert("RGB")
    return tiles


def _load_interior_icons() -> dict:
    """加载所有 interior icon PNG, 返回 {category: Image}"""
    icons = {}
    for cat in INTERIOR_CATS:
        path = TILE_DIR / f"interior_{cat}.png"
        if path.exists():
            icons[cat] = Image.open(path).convert("RGBA")
    return icons


TILES = _load_tiles()
USE_TILES = len(TILES) == 8
if USE_TILES:
    print(f"[grid_preview] 用真实 tile 渲染 ({len(TILES)} 个)")

INTERIOR_ICONS = _load_interior_icons()
print(f"[grid_preview] 用 interior icon ({len(INTERIOR_ICONS)} 个)")

POI_PALETTE = {
    "scenic": (100, 200, 100),
    "food":   (255, 140, 60),
    "shop":   (200, 100, 220),
    "life":   (80, 180, 220),
    "default": (255, 220, 100),
}

CELL_SIZE = 16
PATH_COLOR = (244, 102, 25)
GRID_LINE = (0, 0, 0, 30)
# P1.2 建筑高度
HEIGHT_PX_PER_LEVEL = 4   # 每层 4px 抬高 (跟 Godot 端一致)


def render_grid_to_png(grid, path=None, pois=None, title="", out_path=None,
                       building_heights=None, interiors=None):
    """把 grid + path + pois 渲染成 PNG
    grid: [[int, ...], ...]
    path: [{x, y}, ...]
    pois: [{grid_x, grid_y, name, category, ...}, ...]
    building_heights: P1.2 [[h, ...], ...] 跟 grid 同步, 0=无
    interiors: P1.3 [{name, category, grid_x, grid_y, ...}, ...]
    """
    if not grid:
        raise ValueError("grid 为空")
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0

    title_h = 40 if title else 0
    img_w = w * CELL_SIZE
    # P1.2: 建筑高度图要更高 canvas, 容纳抬高部分
    height_extra = 0
    if building_heights:
        max_h = max((v for row in building_heights for v in row), default=0)
        height_extra = max_h * HEIGHT_PX_PER_LEVEL
    img_h = h * CELL_SIZE + title_h + height_extra

    img = Image.new("RGB", (img_w, img_h), (38, 51, 77))
    draw = ImageDraw.Draw(img, "RGBA")

    # 标题
    if title:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        draw.text((10, 8), title, fill=(255, 220, 100), font=font)

    # 字体备用
    try:
        font_small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 9)
    except OSError:
        font_small = ImageFont.load_default()

    # 画每个 cell (tile 在 P1.2 还是原位画, 高度图叠加在上面)
    for y in range(h):
        for x in range(w):
            cell = grid[y][x] if x < len(grid[y]) else 0
            x0, y0 = x * CELL_SIZE, title_h + y * CELL_SIZE
            if USE_TILES and cell in TILES:
                # P1.1: paste tile
                img.paste(TILES[cell], (x0, y0))
            else:
                # fallback: flat color
                color = PALETTE.get(cell, (0, 0, 0))
                draw.rectangle([x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE], fill=color)

    # P1.2: 画建筑高度图 (抬高多边形 + 阴影)
    if building_heights:
        s = CELL_SIZE
        for y in range(h):
            if y >= len(building_heights):
                break
            hrow = building_heights[y]
            for x in range(w):
                if x >= len(hrow):
                    break
                levels = hrow[x]
                if levels <= 0:
                    continue
                h_px = levels * HEIGHT_PX_PER_LEVEL
                cx = x * s + s * 0.5
                cy = title_h + y * s + s * 0.5
                # 阴影
                shadow_color = (0, 0, 0, int(255 * 0.45))
                draw.polygon([
                    (cx - s * 0.55, cy + s * 0.50 + 2),
                    (cx + s * 0.55, cy + s * 0.50 + 2),
                    (cx + s * 0.65, cy + s * 0.50 + 2 + h_px * 0.3),
                    (cx - s * 0.65, cy + s * 0.50 + 2 + h_px * 0.3),
                ], fill=shadow_color)
                # 侧面 (顶层亮色)
                side_color = (180, 140, 100)
                draw.polygon([
                    (cx - s * 0.4, cy + s * 0.3),
                    (cx + s * 0.4, cy + s * 0.3),
                    (cx + s * 0.45, cy + s * 0.3 - h_px),
                    (cx - s * 0.45, cy + s * 0.3 - h_px),
                ], fill=side_color)
                # 屋顶
                draw.polygon([
                    (cx - s * 0.45, cy + s * 0.3 - h_px),
                    (cx + s * 0.45, cy + s * 0.3 - h_px),
                    (cx + s * 0.35, cy + s * 0.3 - h_px - 2),
                    (cx - s * 0.35, cy + s * 0.3 - h_px - 2),
                ], fill=(80, 50, 30))

    # P1.3: 画 interior slot icon (在 building 中心 cell 上贴)
    if interiors:
        for slot in interiors:
            cat = slot.get("category", "")
            gx = int(slot.get("grid_x", -1))
            gy = int(slot.get("grid_y", -1))
            if gx < 0 or gy < 0 or gx >= w or gy >= h:
                continue
            if cat not in INTERIOR_ICONS:
                continue
            # 贴在 cell 中央 (offset 抵消 title_h)
            ix = gx * s
            iy = title_h + gy * s
            img.paste(INTERIOR_ICONS[cat], (ix, iy), INTERIOR_ICONS[cat])
            # 名字 label (有名字才画)
            if slot.get("has_name"):
                name = slot.get("name", "")
                if name:
                    # 显示在 cell 下方
                    label_y = iy + s + 1
                    if label_y < img_h - 12:
                        try:
                            fnt = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 8)
                        except OSError:
                            fnt = ImageFont.load_default()
                        # 居中, 截断
                        display = name[:6] + ".." if len(name) > 6 else name
                        draw.text((ix - 2, label_y), display, fill=(255, 255, 255),
                                  font=fnt, stroke_width=1, stroke_fill=(0, 0, 0))

    # 画路径 (橙色)
    if path and len(path) >= 2:
        for i in range(len(path) - 1):
            x0 = path[i].get("x", 0) * CELL_SIZE + CELL_SIZE // 2
            y0 = title_h + path[i].get("y", 0) * CELL_SIZE + CELL_SIZE // 2
            x1 = path[i + 1].get("x", 0) * CELL_SIZE + CELL_SIZE // 2
            y1 = title_h + path[i + 1].get("y", 0) * CELL_SIZE + CELL_SIZE // 2
            draw.line([x0, y0, x1, y1], fill=PATH_COLOR, width=3)
        sx = path[0].get("x", 0) * CELL_SIZE + CELL_SIZE // 2
        sy = title_h + path[0].get("y", 0) * CELL_SIZE + CELL_SIZE // 2
        ex = path[-1].get("x", 0) * CELL_SIZE + CELL_SIZE // 2
        ey = title_h + path[-1].get("y", 0) * CELL_SIZE + CELL_SIZE // 2
        draw.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=(0, 255, 0))
        draw.ellipse([ex - 5, ey - 5, ex + 5, ey + 5], fill=(255, 0, 0))

    # P0.3: 画 POI 标记 (彩色圆点 + 名字)
    if pois:
        for poi in pois:
            gx = int(poi.get("grid_x", 0))
            gy = int(poi.get("grid_y", 0))
            if gx < 0 or gy < 0 or gx >= w or gy >= h:
                continue
            cat = poi.get("category", "")
            color = POI_PALETTE.get(cat, POI_PALETTE["default"])
            cx = gx * CELL_SIZE + CELL_SIZE // 2
            cy = title_h + gy * CELL_SIZE + CELL_SIZE // 2
            r = 8
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(0, 0, 0), width=1)
            r2 = 3
            draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(255, 255, 255))
            name = poi.get("name", "")
            if name:
                display_name = name[:8] + ".." if len(name) > 8 else name
                draw.text((cx - 30, cy - r - 12), display_name, fill=(255, 255, 255),
                          font=font_small, stroke_width=1, stroke_fill=(0, 0, 0))

    if out_path is None:
        out_path = PROJECT_ROOT / "exports" / "grid_preview.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        log_path = PROJECT_ROOT / "saved_logs" / args.log
    if not log_path.exists():
        print(f"找不到 log: {args.log}")
        sys.exit(1)
    with open(log_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    title = f"{log_path.stem} | {data.get('meta', {}).get('title', '')}"
    out = Path(args.out) if args.out else None
    out_path = render_grid_to_png(
        data["map"]["grid"],
        data.get("path", []),
        pois=data.get("pois", []),
        title=title,
        out_path=out,
        building_heights=data.get("map", {}).get("building_heights"),
        interiors=data.get("interiors", []),
    )
    print(f"生成 {out_path}")


if __name__ == "__main__":
    main()
