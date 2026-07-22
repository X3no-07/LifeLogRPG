"""P1.3 室内 icon 生成器 (16x16 GBA 风格 + 4x3 sheet)

13 类室内 icon:
  cafe / restaurant / shop / office / hotel / hospital / bank /
  school / museum / pharmacy / library / fitness / theater

每个 icon 是 16x16, 程序化画, 输出到 assets/tiles/interior_*.png
+ 一张 4x4 sheet (interior_sheet.png) 供 Godot 单 texture 加载

设计:
- 12x12 主图形 (中间 4 边留 2px padding)
- 3-4 色: 主色 + 高光 + 阴影 + 1 个细节色
- 像素艺术, 1x1 笔触
"""
import random
from pathlib import Path
from PIL import Image, ImageDraw

TILE_SIZE = 16
SEED = 42


def _new() -> Image.Image:
    return Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))   # 透明背景


def _put(img: Image.Image, x: int, y: int, color: tuple) -> None:
    if 0 <= x < TILE_SIZE and 0 <= y < TILE_SIZE:
        img.putpixel((x, y), color)


# 调色板 (跟 tile 一致, 但每类有主题色)
COLORS = {
    "cafe":       {"base": (130, 80, 40),    "light": (180, 120, 60),  "dark": (90, 50, 20),   "detail": (240, 240, 240)},
    "restaurant": {"base": (220, 80, 60),    "light": (250, 140, 100), "dark": (160, 40, 30),  "detail": (255, 255, 255)},
    "shop":       {"base": (200, 100, 220),  "light": (240, 160, 250), "dark": (140, 60, 160), "detail": (255, 255, 255)},
    "office":     {"base": (100, 130, 180),  "light": (140, 170, 220), "dark": (60, 90, 140),  "detail": (240, 240, 240)},
    "hotel":      {"base": (180, 100, 60),   "light": (220, 150, 100), "dark": (130, 70, 30),  "detail": (255, 240, 100)},
    "hospital":   {"base": (240, 60, 60),    "light": (250, 100, 100), "dark": (180, 30, 30),  "detail": (255, 255, 255)},
    "bank":       {"base": (60, 140, 80),    "light": (100, 180, 120), "dark": (30, 100, 50),  "detail": (255, 220, 100)},
    "school":     {"base": (100, 80, 160),   "light": (140, 120, 200), "dark": (70, 50, 120),  "detail": (240, 220, 100)},
    "museum":     {"base": (140, 100, 60),   "light": (180, 140, 100), "dark": (100, 70, 30),  "detail": (240, 220, 180)},
    "pharmacy":   {"base": (60, 160, 100),   "light": (100, 200, 140), "dark": (30, 120, 70),  "detail": (240, 60, 60)},
    "library":    {"base": (100, 70, 40),    "light": (140, 100, 70),  "dark": (70, 40, 20),   "detail": (240, 220, 180)},
    "fitness":    {"base": (200, 80, 60),    "light": (240, 130, 100), "dark": (140, 50, 30),  "detail": (60, 60, 60)},
    "theater":    {"base": (160, 60, 140),   "light": (200, 100, 180), "dark": (110, 30, 90),  "detail": (240, 220, 100)},
}


def _circle(img: Image.Image, cx: float, cy: float, r: float, color: tuple) -> None:
    """中点圆算法 (GBA 风格, 整数 8-way 对称)"""
    cx_i, cy_i = int(cx * 8), int(cy * 8)
    r_i = int(r * 8)
    # 简化: 用 PIL 的 ellipse, 但缩到 GBA 风格 (用 NEAREST)
    overlay = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).ellipse(
        [cx - r, cy - r, cx + r, cy + r], fill=color
    )
    img.alpha_composite(overlay)


def _rect(img: Image.Image, x0: int, y0: int, x1: int, y1: int, color: tuple) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            _put(img, x, y, color)


# ------------------------------------------------------------------
#  各 icon 画法 (GBA 风格, 16x16, 主图 12x12)
# ------------------------------------------------------------------

def _draw_cafe(img):
    """咖啡杯: 棕色杯 + 白色把手 + 蒸汽"""
    c = COLORS["cafe"]
    # 杯身 (中心梯形 8x6)
    for y in range(7, 14):
        for x in range(5, 11):
            _put(img, x, y, c["base"])
    # 杯沿 (3 像素)
    for x in range(4, 12):
        _put(img, x, 6, c["light"])
    # 把手 (右边)
    for y in range(8, 12):
        _put(img, 11, y, c["light"])
        _put(img, 12, y, c["dark"])
    # 杯底深色
    for x in range(5, 11):
        _put(img, x, 13, c["dark"])
    # 蒸汽 (3 个 dot)
    _put(img, 7, 3, c["detail"])
    _put(img, 8, 2, c["detail"])
    _put(img, 9, 3, c["detail"])


def _draw_restaurant(img):
    """餐厅: 刀 + 叉 (对角线交叉)"""
    c = COLORS["restaurant"]
    # 刀 (左上 -> 右下斜线)
    for i in range(3, 13):
        _put(img, i, i - 3, c["base"])
        _put(img, i, i - 2, c["light"])
    # 叉 (右上 -> 左下斜线)
    for i in range(3, 13):
        _put(img, 15 - i, i - 3, c["dark"])
        _put(img, 14 - i, i - 2, c["light"])
    # 叉头 (4 根线)
    for y in range(2, 4):
        _put(img, 5, y, c["dark"])
        _put(img, 7, y, c["dark"])
        _put(img, 9, y, c["dark"])
        _put(img, 11, y, c["dark"])


def _draw_shop(img):
    """商店: 购物袋 (梯形 + 2 个把手)"""
    c = COLORS["shop"]
    # 袋身
    for y in range(5, 14):
        for x in range(4, 12):
            _put(img, x, y, c["base"])
    # 顶 (亮色)
    for x in range(4, 12):
        _put(img, x, 5, c["light"])
    # 左把手
    for y in range(2, 6):
        _put(img, 5, y, c["dark"])
    for x in range(5, 7):
        _put(img, x, 2, c["dark"])
    # 右把手
    for y in range(2, 6):
        _put(img, 10, y, c["dark"])
    for x in range(9, 11):
        _put(img, x, 2, c["dark"])
    # 装饰: 中间一条横线
    for x in range(4, 12):
        _put(img, x, 9, c["dark"])


def _draw_office(img):
    """办公室: 文件 (3 摞纸)"""
    c = COLORS["office"]
    # 底层文件
    for y in range(8, 13):
        for x in range(4, 12):
            _put(img, x, y, c["dark"])
    # 中层文件
    for y in range(6, 12):
        for x in range(5, 11):
            _put(img, x, y, c["base"])
    # 顶层文件
    for y in range(4, 11):
        for x in range(6, 10):
            _put(img, x, y, c["light"])
    # 顶层文件折角 (右上)
    _put(img, 9, 4, c["detail"])
    _put(img, 9, 5, c["detail"])


def _draw_hotel(img):
    """酒店: 床 + 枕头"""
    c = COLORS["hotel"]
    # 床架
    for y in range(7, 13):
        for x in range(3, 13):
            _put(img, x, y, c["base"])
    # 床头
    for x in range(3, 13):
        _put(img, x, 7, c["light"])
    # 枕头
    for y in range(8, 10):
        for x in range(4, 7):
            _put(img, x, y, c["detail"])
    # 床腿
    for y in range(13, 15):
        for x in [3, 4, 11, 12]:
            _put(img, x, y, c["dark"])


def _draw_hospital(img):
    """医院: 红色十字"""
    c = COLORS["hospital"]
    # 白色方块
    for y in range(4, 12):
        for x in range(4, 12):
            _put(img, x, y, c["detail"])
    # 红色十字 (横)
    for x in range(4, 12):
        _put(img, x, 7, c["base"])
        _put(img, x, 8, c["base"])
    # 红色十字 (竖)
    for y in range(4, 12):
        _put(img, 7, y, c["base"])
        _put(img, 8, y, c["base"])


def _draw_bank(img):
    """银行: 圆顶 + ¥符号"""
    c = COLORS["bank"]
    # 圆顶
    for y in range(3, 7):
        for x in range(4, 12):
            if abs(x - 7.5) < 7 - y:
                _put(img, x, y, c["light"])
    # 柱体
    for y in range(7, 13):
        for x in range(4, 12):
            _put(img, x, y, c["base"])
    # 底座
    for x in range(3, 13):
        _put(img, x, 13, c["dark"])
    # 柱子分隔 (3 根)
    for x in [6, 8, 10]:
        for y in range(7, 13):
            _put(img, x, y, c["dark"])


def _draw_school(img):
    """学校: 苹果 + 铅笔"""
    c = COLORS["school"]
    # 苹果身
    for y in range(6, 12):
        for x in range(5, 11):
            if (x - 7.5) ** 2 + (y - 9) ** 2 < 9:
                _put(img, x, y, c["light"] if (x + y) % 2 == 0 else c["base"])
    # 苹果柄
    _put(img, 8, 4, c["dark"])
    _put(img, 9, 5, c["dark"])
    # 苹果叶
    _put(img, 10, 4, c["detail"])


def _draw_museum(img):
    """博物馆: 柱子 + 三角山墙"""
    c = COLORS["museum"]
    # 山墙 (三角)
    for y in range(2, 6):
        for x in range(7 - (y - 2), 9 + (y - 1)):
            _put(img, x, y, c["light"])
    # 顶线
    for x in range(2, 14):
        _put(img, x, 5, c["dark"])
    # 柱体
    for x in [3, 6, 9, 12]:
        for y in range(6, 13):
            _put(img, x, y, c["base"])
    # 底
    for x in range(2, 14):
        _put(img, x, 13, c["dark"])


def _draw_pharmacy(img):
    """药店: 药丸 (2 个圆, 红色 + 白色)"""
    c = COLORS["pharmacy"]
    # 药丸斜放
    # 红色半
    for y in range(5, 11):
        for x in range(4, 12):
            if (x - 7.5) ** 2 + (y - 7.5) ** 2 < 9:
                if x < 7:
                    _put(img, x, y, c["base"])
                else:
                    _put(img, x, y, c["detail"])
    # 中心分隔
    for y in range(5, 11):
        _put(img, 7, y, c["dark"])
        _put(img, 8, y, c["dark"])


def _draw_library(img):
    """图书馆: 摞书 (3 本横)"""
    c = COLORS["library"]
    # 底层 (宽)
    for y in range(11, 14):
        for x in range(3, 13):
            _put(img, x, y, c["base"])
    # 中层
    for y in range(8, 11):
        for x in range(4, 12):
            _put(img, x, y, c["light"])
    # 顶层 (窄)
    for y in range(5, 8):
        for x in range(5, 11):
            _put(img, x, y, c["dark"])
    # 中线 (书脊)
    for x in [4, 8, 12]:
        if 11 <= 14:
            pass
    # 顶书中间竖线
    for y in range(5, 8):
        _put(img, 7, y, c["detail"])
        _put(img, 8, y, c["detail"])


def _draw_fitness(img):
    """健身房: 哑铃 (2 球 + 1 杠)"""
    c = COLORS["fitness"]
    # 左球
    for y in range(5, 11):
        for x in range(2, 6):
            if (x - 3.5) ** 2 + (y - 7.5) ** 2 < 4:
                _put(img, x, y, c["light"] if (x + y) % 2 == 0 else c["base"])
    # 右球
    for y in range(5, 11):
        for x in range(10, 14):
            if (x - 12.5) ** 2 + (y - 7.5) ** 2 < 4:
                _put(img, x, y, c["light"] if (x + y) % 2 == 0 else c["base"])
    # 杠
    for y in [7, 8]:
        for x in range(4, 12):
            _put(img, x, y, c["dark"])


def _draw_theater(img):
    """剧院: 帷幕 (顶部帘 + 笑脸)"""
    c = COLORS["theater"]
    # 顶部帘 (锯齿)
    for x in range(3, 13):
        if (x // 2) % 2 == 0:
            for y in range(2, 5):
                _put(img, x, y, c["light"])
        else:
            for y in range(3, 5):
                _put(img, x, y, c["light"])
    # 主体 (深色)
    for y in range(5, 13):
        for x in range(3, 13):
            _put(img, x, y, c["base"])
    # 装饰: 中间 2 个黄星
    _put(img, 7, 8, c["detail"])
    _put(img, 8, 8, c["detail"])
    _put(img, 7, 10, c["detail"])
    _put(img, 8, 10, c["detail"])


# category -> drawer
DRAWERS = {
    "cafe": _draw_cafe,
    "restaurant": _draw_restaurant,
    "shop": _draw_shop,
    "office": _draw_office,
    "hotel": _draw_hotel,
    "hospital": _draw_hospital,
    "bank": _draw_bank,
    "school": _draw_school,
    "museum": _draw_museum,
    "pharmacy": _draw_pharmacy,
    "library": _draw_library,
    "fitness": _draw_fitness,
    "theater": _draw_theater,
}


def generate_all(out_dir: Path) -> list:
    """生成所有 icon + 4x4 sheet"""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for cat, drawer in DRAWERS.items():
        img = _new()
        drawer(img)
        path = out_dir / f"interior_{cat}.png"
        img.save(path)
        results.append((cat, path, img.size))
        print(f"  [interior] {cat}.png  size={img.size}")
    # 4x4 sheet (16 个 slot, 13 个用, 3 个空)
    sheet_w = TILE_SIZE * 4   # 64
    sheet_h = TILE_SIZE * 4   # 64
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for i, (cat, _, _) in enumerate(results):
        col = i % 4
        row = i // 4
        tile = Image.open(out_dir / f"interior_{cat}.png")
        sheet.paste(tile, (col * TILE_SIZE, row * TILE_SIZE), tile)
    sheet_path = out_dir / "interior_sheet.png"
    sheet.save(sheet_path)
    print(f"  [interior] sheet: interior_sheet.png  size={sheet.size}")
    return results


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    out = project_root / "assets" / "tiles"
    print(f"[generate_interior_icons] 输出: {out}")
    results = generate_all(out)
    print(f"[generate_interior_icons] 完成: {len(results)} 个 icon + 1 sheet")
