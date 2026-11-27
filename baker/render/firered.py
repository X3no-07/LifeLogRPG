"""FireRed 风格地图渲染器 (baker 内置, 产品代码).

把烘焙出的网格 + OSM 矢量数据画成一张 320x240 的火红风地图,
以后每次烘焙都自动走它, 不再手跑散脚本。

来源: map-preview-firered 里 render5.py (故宫) / render_ouc.py (海大) /
render_jining.py (济宁) / render_hangzhou.py (杭州) 四份脚本的公共核心,
抽成一个通用函数。去掉的东西 (都是某一处的手调, 不通用):
  - 试玩帧 / 角色精灵 / 对话框 / HUD (那是试玩页的事, 不归 baker)
  - 恒丰国际产业园单栋手调块 (通用描边已能画旋转楼, 见 vector_buildings)
  - 故宫金顶矩形等地名写死的坐标
  - 西湖多边形 relation 的手工 inner-ring 处理 (见下: 水体改走通用兜底)
留下的通用规则 (不写死任何地名、坐标):
  - 矢量楼: 大楼按自身描边轮廓画成一体 (屋顶分色、脊线、描边、门窗),
    小楼留瓦片风; 屋顶按 OSM 多边形分片, 避免整片并成一张平板
  - 平滑草地 / 铺装: 整图一级低频纹理, 不按格子填色, 不出方格
  - 矢量路: OSM 折线画直路, 路缘 + 路面 + 虚线中线; 平行车道合并成一条
  - 矢量水: OSM 水线 / 水面画平滑水带, 桥面盖住水; 另有网格水体兜底
    (OSM 多边形 relation 的外环 way 常无标签、进不了 parsed_osm,
    比如西湖, 但栅格化后的网格里有水格: 大片水格按描边轮廓补画成水面,
    围住的陆地 (堤 / 岛) 再从快照里恢复, 不用为每个湖手调)
  - 树: 每格一棵圆树冠; 小楼阴影
  - 路线红线: 只画步行 / 骑行段 (开车 / 公交的 teleport 点不断线),
    先视线法平滑再画, 沿路走、无斜线、无楼梯状
  - 地标金顶: POI 名里含"故宫" / "午门"时, 其周边的楼群按金顶红墙画。
    这是按 POI 名字触发的通用地标规则 (名字来自烘焙的 POI 数据,
    不是写死坐标); 没有这类 POI 的地方完全不受影响。

接口:
    render_firered_map(grid, building_heights=None, path=None, pois=None,
                       osm=None, bbox=None, output_path=None,
                       start_name="", end_name="") -> PIL.Image.Image
  - grid: 烘焙网格, cell 码跟 baker.core.gridifier 一致
    (0 草 1 路 2 楼 3 水 4 树 5 人行道 6 POI 7 广场)
  - building_heights: 同尺寸层数表, 可省
  - path: 路径点, [{"x","y","transport"}] 或 (x, y) 元组; transport
    非 walking/bicycling 的点不进红线 (driving/transit 是跳点)
  - pois: [{"name","grid_x","grid_y"}] 或同名属性的对象, 用于通用标注
  - osm: baker.clients.osm.parse_overpass 的输出
    (roads/buildings/water/green/ground, 节点为 (lng, lat) WGS84)
  - bbox: 切片 bbox (min_lat, min_lng, max_lat, max_lng), 跟 grid 同系;
    osm 给了但 bbox 没给时, 矢量层跳过、只按网格画, 不报错
  - output_path: 给了就存 PNG, 不给只返回 Image
输出尺寸: W*T x H*T, T=16; 320x240 网格即 5120x3840。
渲染失败由调用方兜底 (baker 写 JSON 是主流程, 画图挂了也不能丢 JSON)。
"""
import math
import os
import random
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont

from ..core.gridifier import (
    HIGHWAY_WIDTH,
    _project_floats,
    smooth_path_on_grid,
)
from .vector_buildings import (
    completion_buildings,
    draw_building,
    draw_roof_piece,
    draw_under_patches,
    fill_missing_cells,
    polygon_grid_cells,
    recovered_buildings,
    roof_palette,
    roof_pieces,
    trace_blob_outline,
    trace_large_blobs,
)

T = 16
GRASS, ROAD, BUILDING, WATER, TREE, SIDEWALK, POI, PLAZA = 0, 1, 2, 3, 4, 5, 6, 7

C = {
    "grass": (110, 190, 70),
    "road": (126, 126, 112),
    "road_edge": (62, 62, 54),
    "road_line": (236, 236, 208),
    "curb": (196, 186, 152),
    "walk": (200, 186, 150),
    "walk_dk": (152, 138, 106),
    "plaza": (204, 202, 192),
    "paved": (204, 202, 192),
    "parking": (176, 176, 168),
    "dirt": (188, 164, 116),
    "water": (56, 118, 214),
    "water_lt": (122, 180, 242),
    "water_dk": (32, 80, 168),
    "tree_dk": (22, 88, 22),
    "tree": (44, 146, 44),
    "tree_lt": (112, 202, 92),
    "trunk": (107, 74, 42),
    "roof_a": (198, 86, 48),
    "roof_a_lt": (236, 128, 78),
    "roof_a_dk": (140, 56, 32),
    "roof_c": (92, 112, 142),
    "roof_c_lt": (132, 156, 186),
    "roof_c_dk": (60, 76, 102),
    "wall": (238, 216, 168),
    "wall_dk": (182, 158, 112),
    "window": (58, 82, 124),
    "window_lt": (140, 180, 220),
    "door": (122, 82, 42),
    "door_dk": (88, 58, 28),
    "outline": (48, 40, 32),
    "route": (220, 40, 40),
    "route_start": (60, 180, 60),
}

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

# 地面网格码 (ground sidecar, 跟预览 export_ground 一致):
# 0 铺装默认, 1 草, 2 广场, 3 停车场, 4 裸土
GROUND_KIND_CODE = {"grass": 1, "plaza": 2, "parking": 3, "dirt": 4}
_MAJOR_ROADS = {"trunk", "primary", "secondary", "tertiary"}
_LANE_GROUP_DIST = 6.0
_LANE_GROUP_OVERLAP = 0.30
_BRIDGE_DIST = 1.5


# ---------------------------------------------------------------------------
#  OSM (lng, lat) -> 矢量 sidecar (float grid 坐标)
# ---------------------------------------------------------------------------
def _osm_to_sidecars(osm, bbox, grid_size):
    """parsed_osm -> (roads, water, buildings, ground_grid)。
    roads: [{"pts": [(fx, fy)], "w": cells, "type": highway}]
    water: [{"pts": [...], "closed": bool}]
    buildings: [{"pts", "levels", "name", "area", "w", "h"}]
    ground_grid: HxW, 码见 GROUND_KIND_CODE (0=铺装默认)。
    osm 为空时全返回空, 调用方只按网格画。"""
    w, h = grid_size
    roads, water, buildings = [], [], []
    ground_grid = [[0] * w for _ in range(h)]
    if not osm:
        return roads, water, buildings, ground_grid
    for r in osm.get("roads", []) or []:
        pts = _project_floats(r.get("nodes", []), bbox, grid_size)
        clean = [pts[0]] if pts else []
        for p in pts[1:]:
            if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 0.05:
                clean.append(p)
        if len(clean) >= 2:
            roads.append({"pts": clean,
                          "w": HIGHWAY_WIDTH.get(r.get("highway_type", ""), 1),
                          "type": r.get("highway_type", "")})
    for wseg in osm.get("water", []) or []:
        nodes = wseg.get("nodes", [])
        pts = _project_floats(nodes, bbox, grid_size)
        if len(pts) >= 2:
            closed = len(nodes) >= 3 and nodes[0] == nodes[-1]
            holes = []
            for hole in wseg.get("holes", []) or []:
                hpts = _project_floats(hole, bbox, grid_size)
                if len(hpts) >= 3:
                    holes.append(hpts)
            water.append({"pts": pts, "closed": closed, "holes": holes})
    for b in osm.get("buildings", []) or []:
        pts = _project_floats(b.get("nodes", []), bbox, grid_size)
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        area = abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
                       - pts[(i + 1) % len(pts)][0] * pts[i][1]
                       for i in range(len(pts))) * 0.5)
        buildings.append({"pts": pts, "levels": b.get("levels", 1),
                          "name": b.get("name", ""), "area": area,
                          "w": max(xs) - min(xs), "h": max(ys) - min(ys)})
    # 地面: dirt/parking/plaza/grass 依次画, 草最后 (平局草赢), 跟 osm_to_grid 一致
    if osm.get("ground"):
        gimg = Image.new("L", (w, h), 0)
        gd = ImageDraw.Draw(gimg)
        for kind in ("dirt", "parking", "plaza", "grass"):
            code = GROUND_KIND_CODE[kind]
            for g in osm["ground"]:
                if g.get("kind") != kind:
                    continue
                pts = _project_floats(g.get("nodes", []), bbox, grid_size)
                if len(pts) >= 3:
                    gd.polygon(pts, fill=code)
        px = gimg.load()
        ground_grid = [[px[x, y] for x in range(w)] for y in range(h)]
    return roads, water, buildings, ground_grid


# ---------------------------------------------------------------------------
#  输入归一化
# ---------------------------------------------------------------------------
def _norm_path(path):
    """路径点 -> [(x, y, transport)]。dict / Waypoint 对象 / (x, y) 元组都接受。"""
    out = []
    for p in path or []:
        if isinstance(p, dict):
            out.append((int(p["x"]), int(p["y"]),
                        str(p.get("transport", "walking"))))
        elif isinstance(p, (tuple, list)):
            out.append((int(p[0]), int(p[1]), "walking"))
        else:
            out.append((int(getattr(p, "x")), int(getattr(p, "y")),
                        str(getattr(p, "transport", "walking"))))
    return out


def _norm_pois(pois):
    """POI -> [(name, grid_x, grid_y, category)]。"""
    out = []
    for p in pois or []:
        if isinstance(p, dict):
            out.append((str(p.get("name", "")), int(p.get("grid_x", -1)),
                        int(p.get("grid_y", -1)), str(p.get("category", ""))))
        else:
            out.append((str(getattr(p, "name", "")), int(getattr(p, "grid_x", -1)),
                        int(getattr(p, "grid_y", -1)),
                        str(getattr(p, "category", ""))))
    return [(n, x, y, c) for n, x, y, c in out if n and x >= 0 and y >= 0]


# 值得标在地图上的 POI 分类 (餐馆 / 商店 / 酒店不标, 否则满图都是店名)
_LABEL_CATEGORIES = {"scenic", "leisure", "edu", "public", "transport", "gov"}


# ---------------------------------------------------------------------------
#  瓦片 (平铺底色; 屋顶/墙按参数缓存, 避免 76800 格重复建图)
# ---------------------------------------------------------------------------
def _flat(color):
    return Image.new("RGB", (T, T), color)


def _hline(im, x0, x1, y, col):
    for x in range(max(0, x0), min(T, x1 + 1)):
        if 0 <= y < T:
            im.putpixel((x, y), col)


def _vline(im, x, y0, y1, col):
    for y in range(max(0, y0), min(T, y1 + 1)):
        if 0 <= x < T:
            im.putpixel((x, y), col)


def _rect(im, x0, y0, x1, y1, col):
    for y in range(max(0, y0), min(T, y1 + 1)):
        _hline(im, x0, x1, y, col)


def _tree_tile():
    im = _flat(C["grass"])
    _rect(im, 9, 13, 14, 14, (70, 138, 44))  # 地面阴影
    _rect(im, 7, 11, 8, 13, C["trunk"])
    rows = [(4, 11), (3, 12), (2, 13), (2, 13), (2, 13),
            (3, 12), (3, 12), (4, 11), (5, 10), (6, 9)]
    for i, (x0, x1) in enumerate(rows):
        _hline(im, x0, x1, 2 + i, C["tree"])
        im.putpixel((x0, 2 + i), C["tree_dk"])
        im.putpixel((x1, 2 + i), C["tree_dk"])
    _hline(im, 4, 11, 2, C["tree_dk"])
    for (x, y) in ((4, 3), (5, 3), (6, 4), (5, 5), (10, 4)):
        im.putpixel((x, y), C["tree_lt"])
    return im


class _Tiles:
    """底色瓦片缓存: 平铺的只建一次, 屋顶/墙按 (参数) 缓存。"""

    def __init__(self):
        self.grass = _flat(C["grass"])
        self.plaza = _flat(C["plaza"])
        self.paved = _flat(C["paved"])
        self.parking = _flat(C["parking"])
        self.dirt = _flat(C["dirt"])
        self.road = _flat(C["road"])
        self.tree = _tree_tile()
        self.walk = self._sidewalk()
        self.poi = self._poi()
        self._roof = {}
        self._wall = {}

    @staticmethod
    def _sidewalk():
        im = _flat(C["walk"])
        _hline(im, 0, 15, 0, C["walk_dk"])
        _hline(im, 0, 15, 15, C["walk_dk"])
        _vline(im, 0, 0, 15, C["walk_dk"])
        _vline(im, 15, 0, 15, C["walk_dk"])
        _hline(im, 1, 14, 7, C["walk_dk"])
        _vline(im, 7, 1, 14, C["walk_dk"])
        return im

    def _poi(self):
        im = _flat(C["grass"])
        _rect(im, 5, 2, 10, 8, (220, 48, 48))
        _rect(im, 6, 3, 9, 7, (255, 255, 255))
        im.putpixel((7, 4), (220, 48, 48))
        im.putpixel((8, 5), (220, 48, 48))
        _vline(im, 7, 9, 12, C["outline"])
        return im

    def roof(self, band, edges, variant=0, is_top=False, seam=False):
        key = (band, tuple(sorted(edges)), variant, is_top, seam)
        if key in self._roof:
            return self._roof[key]
        palettes = [
            (C["roof_a"], C["roof_a_lt"], C["roof_a_dk"]),
            ((150, 100, 60), (190, 140, 95), (104, 66, 38)),
            (C["roof_c"], C["roof_c_lt"], C["roof_c_dk"]),
            ((96, 96, 108), (132, 132, 146), (62, 62, 72)),
            ((214, 166, 58), (238, 198, 100), (160, 116, 30)),
        ]
        base, lt, dk = palettes[variant % len(palettes)]
        if variant != 4:
            if band >= 5:
                base, lt, dk = palettes[2]
            elif band >= 3 and variant == 0:
                base, lt, dk = palettes[1]
        im = Image.new("RGB", (T, T), base)
        for band_y in range(2, 16, 3):
            _hline(im, 0, 15, band_y, lt)
            _hline(im, 0, 15, band_y + 2, dk)
            off = 4 if (band_y // 3) % 2 == 0 else 10
            for x in range(off, 16, 8):
                _vline(im, x, band_y, band_y + 1, dk)
        if is_top:
            _hline(im, 0, 15, 0, dk)
            _hline(im, 0, 15, 1, lt)
        if seam:
            _vline(im, 0, 0, 15, dk)
        if "N" in edges:
            _hline(im, 0, 15, 0, C["outline"])
        if "S" in edges:
            _hline(im, 0, 15, 15, C["outline"])
        if "W" in edges:
            _vline(im, 0, 0, 15, C["outline"])
        if "E" in edges:
            _vline(im, 15, 0, 15, C["outline"])
        self._roof[key] = im
        return im

    def wall(self, has_door, has_window, edges, palace=False):
        key = (has_door, has_window, tuple(sorted(edges)), palace)
        if key in self._wall:
            return self._wall[key]
        base = (196, 48, 40) if palace else C["wall"]
        dk = (140, 30, 26) if palace else C["wall_dk"]
        im = Image.new("RGB", (T, T), base)
        if has_window:
            if palace:
                _rect(im, 6, 4, 9, 8, (250, 210, 90))
                _rect(im, 7, 5, 8, 7, (70, 40, 30))
            else:
                _rect(im, 6, 4, 9, 8, C["window"])
                _hline(im, 6, 9, 6, C["window_lt"])
                _vline(im, 7, 4, 8, C["window_lt"])
        _hline(im, 0, 15, 13, dk)
        _hline(im, 0, 15, 14, dk)
        if has_door:
            _rect(im, 6, 9, 9, 15, C["door_dk"])
            _rect(im, 7, 10, 8, 15, C["door"])
            if palace:
                im.putpixel((7, 11), (250, 210, 90))
                im.putpixel((8, 13), (250, 210, 90))
            im.putpixel((8, 12), C["road_line"])
            _hline(im, 5, 10, 15, C["curb"])
        if "W" in edges:
            _vline(im, 0, 0, 15, C["outline"])
        if "E" in edges:
            _vline(im, 15, 0, 15, C["outline"])
        if "S" in edges:
            _hline(im, 0, 15, 15, C["outline"])
        self._wall[key] = im
        return im


def _apply_texture(img, cells, seed, strength):
    """整图一级低频纹理 (小随机图 BICUBIC 放大, 没有格子感),
    只作用在 cells 指定的格子区域, 在矢量层之前画。"""
    if not cells:
        return
    wpx, hpx = img.size
    rnd = random.Random(seed)
    sw, sh = max(2, wpx // 128), max(2, hpx // 128)
    small = Image.new("L", (sw, sh))
    small.putdata([rnd.randrange(256) for _ in range(sw * sh)])
    var = small.resize((wpx, hpx), Image.BICUBIC)
    light = var.point(lambda p: int(max(0, p - 128) * strength))
    dark = var.point(lambda p: int(max(0, 128 - p) * strength))
    tex = ImageChops.subtract(
        ImageChops.add(img, Image.merge("RGB", (light, light, light))),
        Image.merge("RGB", (dark, dark, dark)))
    mask = Image.new("L", (wpx, hpx), 0)
    md = ImageDraw.Draw(mask)
    for (gx, gy) in cells:
        md.rectangle([gx * T, gy * T, gx * T + T - 1, gy * T + T - 1], fill=255)
    img.paste(tex, (0, 0), mask)


# ---------------------------------------------------------------------------
#  矢量路: 平行车道合并 / 桥面分段 / 虚线
# ---------------------------------------------------------------------------
def _road_dir(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xspan = max(xs) - min(xs)
    yspan = max(ys) - min(ys)
    if xspan > 2.0 * max(yspan, 1.0):
        return "EW"
    if yspan > 2.0 * max(xspan, 1.0):
        return "NS"
    return None


def _merge_parallel_lanes(roads):
    """一条大道的双向车道 + 两侧非机动车道画成多条灰带像立交,
    合并成一条宽路: 最长那条做脊线、移到组中线、宽 = 整组横向跨度。
    安全阀: 整组横向跨度 > 12 格 (约 60 米) 时不合并、原样保留——
    弯曲的环路 / 多条平行小路会被误并成一张几百米宽的灰板
    (杭州湖滨路曾并出 65 格宽)。"""
    ew = [r for r in roads if _road_dir(r["pts"]) == "EW"]
    ns = [r for r in roads if _road_dir(r["pts"]) == "NS"]
    other = [r for r in roads if _road_dir(r["pts"]) is None]
    out = list(other)
    rank = {"motorway": 7, "trunk": 6, "primary": 5, "secondary": 4,
            "tertiary": 3, "residential": 2, "service": 1, "footway": 0,
            "cycleway": 0, "pedestrian": 0, "steps": 0}
    for group_roads, is_ew in ((ew, True), (ns, False)):
        n = len(group_roads)
        parent = list(range(n))

        def _find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def _union(a, b):
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(n):
            for j in range(i + 1, n):
                a, b = group_roads[i], group_roads[j]
                if is_ew:
                    ay = sum(p[1] for p in a["pts"]) / len(a["pts"])
                    by = sum(p[1] for p in b["pts"]) / len(b["pts"])
                    if abs(ay - by) > _LANE_GROUP_DIST:
                        continue
                    ax0, ax1 = min(p[0] for p in a["pts"]), max(p[0] for p in a["pts"])
                    bx0, bx1 = min(p[0] for p in b["pts"]), max(p[0] for p in b["pts"])
                    ov = min(ax1, bx1) - max(ax0, bx0)
                    if ov <= 0:
                        continue
                    shorter = min(ax1 - ax0, bx1 - bx0)
                    if shorter > 0 and ov / shorter < _LANE_GROUP_OVERLAP:
                        continue
                else:
                    ax = sum(p[0] for p in a["pts"]) / len(a["pts"])
                    bx = sum(p[0] for p in b["pts"]) / len(b["pts"])
                    if abs(ax - bx) > _LANE_GROUP_DIST:
                        continue
                    ay0, ay1 = min(p[1] for p in a["pts"]), max(p[1] for p in a["pts"])
                    by0, by1 = min(p[1] for p in b["pts"]), max(p[1] for p in b["pts"])
                    ov = min(ay1, by1) - max(ay0, by0)
                    if ov <= 0:
                        continue
                    shorter = min(ay1 - ay0, by1 - by0)
                    if shorter > 0 and ov / shorter < _LANE_GROUP_OVERLAP:
                        continue
                _union(i, j)
        groups = {}
        for i in range(n):
            groups.setdefault(_find(i), []).append(group_roads[i])
        for members in groups.values():
            if len(members) == 1:
                out.append(members[0])
                continue
            spine = max(members, key=lambda r: sum(
                math.hypot(b[0] - a[0], b[1] - a[1])
                for a, b in zip(r["pts"], r["pts"][1:])))
            if is_ew:
                centres = sorted(sum(p[1] for p in r["pts"]) / len(r["pts"])
                                 for r in members)
                med = centres[len(centres) // 2]
                spine_c = sum(p[1] for p in spine["pts"]) / len(spine["pts"])
                pts = [(x, y + (med - spine_c)) for x, y in spine["pts"]]
                lo = min(min(p[1] for p in r["pts"]) - r.get("w", 1) / 2.0
                         for r in members)
                hi = max(max(p[1] for p in r["pts"]) + r.get("w", 1) / 2.0
                         for r in members)
            else:
                centres = sorted(sum(p[0] for p in r["pts"]) / len(r["pts"])
                                 for r in members)
                med = centres[len(centres) // 2]
                spine_c = sum(p[0] for p in spine["pts"]) / len(spine["pts"])
                pts = [(x + (med - spine_c), y) for x, y in spine["pts"]]
                lo = min(min(p[0] for p in r["pts"]) - r.get("w", 1) / 2.0
                         for r in members)
                hi = max(max(p[0] for p in r["pts"]) + r.get("w", 1) / 2.0
                         for r in members)
            if hi - lo > 12.0:
                # 跨度超 12 格不是一条大道, 是弯路 / 多条平行小路连成的串:
                # 不合并, 原样保留各条路, 避免并出一张灰板
                out.extend(members)
                continue
            best = max(members, key=lambda r: rank.get(r.get("type", ""), 0))
            merged = dict(best)
            merged["pts"] = pts
            merged["w"] = max(1, int(round(hi - lo)))
            out.append(merged)
    return out


def _dist_to_path_factory(path_pts):
    segs = [(path_pts[i], path_pts[i + 1]) for i in range(len(path_pts) - 1)]

    def _dist(px, py):
        best = 1e9
        for (ax, ay), (bx, by) in segs:
            vx, vy = bx - ax, by - ay
            wx, wy = px - ax, py - ay
            seg2 = vx * vx + vy * vy
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / seg2))
            best = min(best, math.hypot(px - (ax + t * vx), py - (ay + t * vy)))
        return best

    return _dist


def _road_open(pts):
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 0.5:
        return True
    tot = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    return tot > 3.0


def _keep_roads(all_roads, path_pts):
    """只留路线附近的路 + 全图主干道, 再按连通性向外长 3 轮
    (桥和接路线的小路不断在水边)。没路径时只留主干道。"""
    if path_pts:
        dist_to_path = _dist_to_path_factory(path_pts)
        kept = [r for r in all_roads
                if (min(dist_to_path(x, y) for x, y in r["pts"]) <= 5.0
                    or r["type"] in _MAJOR_ROADS)
                and _road_open(r["pts"])]
    else:
        kept = [r for r in all_roads
                if r["type"] in _MAJOR_ROADS and _road_open(r["pts"])]
    for _round in range(3):
        pts = set()
        for r in kept:
            for p in (r["pts"][0], r["pts"][-1]):
                pts.add((round(p[0]), round(p[1])))
        grew = False
        for r in all_roads:
            if r in kept or not _road_open(r["pts"]):
                continue
            for p in (r["pts"][0], r["pts"][-1]):
                if any(abs(p[0] - qx) <= 2.0 and abs(p[1] - qy) <= 2.0
                       for qx, qy in pts):
                    kept.append(r)
                    grew = True
                    break
        if not grew:
            break
    return kept


def _bridge_runs(pts, water_lines):
    """把一条路按"离水线 <= 1.5 格"切成桥面段 / 普通段。
    桥面段画得比水带宽, 桥面盖住水, 路线不像走在水上。"""
    if len(pts) < 2:
        return [(pts, False)]
    bbs = []
    for wl in water_lines:
        xs = [p[0] for p in wl]
        ys = [p[1] for p in wl]
        bbs.append((min(xs), min(ys), max(xs), max(ys)))
    is_bridge = []
    for (px, py) in pts:
        near = False
        for wl, wb in zip(water_lines, bbs):
            if (wb[0] - _BRIDGE_DIST > px or wb[2] + _BRIDGE_DIST < px
                    or wb[1] - _BRIDGE_DIST > py or wb[3] + _BRIDGE_DIST < py):
                continue
            for j in range(len(wl) - 1):
                ax, ay = wl[j]
                bx, by = wl[j + 1]
                vx, vy = bx - ax, by - ay
                wx, wy = px - ax, py - ay
                s2 = vx * vx + vy * vy
                t = 0.0 if s2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / s2))
                if math.hypot(px - (ax + t * vx), py - (ay + t * vy)) <= _BRIDGE_DIST:
                    near = True
                    break
            if near:
                break
        is_bridge.append(near)
    if not any(is_bridge):
        return [(pts, False)]
    runs = []
    start = 0
    for i in range(1, len(pts)):
        if is_bridge[i] != is_bridge[start]:
            runs.append((pts[start:i + 1], is_bridge[start]))
            start = i
    runs.append((pts[start:], is_bridge[start]))
    return [(r, b) for r, b in runs if len(r) >= 2]


def _dashed(dr, pts, fill, width, dash=9, gap=9):
    cyc = dash + gap
    phase = 0.0
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        seg = math.hypot(bx - ax, by - ay)
        if seg <= 0:
            continue
        ux, uy = (bx - ax) / seg, (by - ay) / seg
        s = 0.0
        while s < seg:
            p = (phase + s) % cyc
            take = min((dash - p) if p < dash else (cyc - p), seg - s)
            if p < dash:
                dr.line([(ax + ux * s, ay + uy * s),
                         (ax + ux * (s + take), ay + uy * (s + take))],
                        fill=fill, width=width)
            s += take
        phase = (phase + seg) % cyc


# ---------------------------------------------------------------------------
#  水体兜底: 网格水格 -> 平滑水面 (OSM relation 外环进不了 parsed_osm 时用)
# ---------------------------------------------------------------------------
def _water_blobs(grid, W, H, min_cells=8):
    """连通的 CELL_WATER 区域, 每个返回 (描边多边形列表, 围住的陆地格)。
    描边用跟楼一样的轮廓追踪 + 简化, 所以湖岸是平滑的不是楼梯;
    围住的陆地 (堤 / 岛, >= 6 格的连通块) 由调用方从快照恢复。"""
    seen = [[False] * W for _ in range(H)]
    out = []
    for y in range(H):
        for x in range(W):
            if grid[y][x] != WATER or seen[y][x]:
                continue
            cells = []
            q = deque([(x, y)])
            seen[y][x] = True
            while q:
                cx, cy = q.popleft()
                cells.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (0 <= nx < W and 0 <= ny < H and grid[ny][nx] == WATER
                            and not seen[ny][nx]):
                        seen[ny][nx] = True
                        q.append((nx, ny))
            if len(cells) < min_cells:
                continue
            polys = []
            for loop in trace_blob_outline(cells):
                if len(loop) < 4:
                    continue
                polys.append(loop)
            if polys:
                out.append((polys, cells))
    return out


def _enclosed_land_cells(grid, W, H, min_cells=6):
    """被水围住的非水格 (堤 / 岛), >= min_cells 格的连通块才算。
    从边界 flood fill 出能到达的格子, 剩下的非水格就是被围住的。"""
    reach = [[False] * W for _ in range(H)]
    q = deque()
    for x in range(W):
        for y in (0, H - 1):
            if grid[y][x] != WATER and not reach[y][x]:
                reach[y][x] = True
                q.append((x, y))
    for y in range(H):
        for x in (0, W - 1):
            if grid[y][x] != WATER and not reach[y][x]:
                reach[y][x] = True
                q.append((x, y))
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if (0 <= nx < W and 0 <= ny < H and grid[ny][nx] != WATER
                    and not reach[ny][nx]):
                reach[ny][nx] = True
                q.append((nx, ny))
    seen = [[False] * W for _ in range(H)]
    holes = []
    for y in range(H):
        for x in range(W):
            if grid[y][x] != WATER and not reach[y][x] and not seen[y][x]:
                comp = []
                qq = deque([(x, y)])
                seen[y][x] = True
                while qq:
                    cx, cy = qq.popleft()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < W and 0 <= ny < H and grid[ny][nx] != WATER
                                and not reach[ny][nx] and not seen[ny][nx]):
                            seen[ny][nx] = True
                            qq.append((nx, ny))
                if len(comp) >= min_cells:
                    holes.extend(comp)
    return holes


def _draw_water_sparkles(dr, water, W, H):
    """水带波光: 开放水线沿线画短亮划线; 闭合水面里撒几条短亮划线。
    确定性随机 (按水体序号取种子), 同一份输入出的图不变。"""
    for wi, wseg in enumerate(water):
        pts = wseg["pts"]
        if wseg["closed"]:
            if len(pts) < 3:
                continue
            rnd = random.Random(1000 + wi)
            cells = polygon_grid_cells(pts, W, H)
            if not cells:
                continue
            for _ in range(min(8, max(2, len(cells) // 200))):
                cx, cy = rnd.choice(cells)
                x0 = (cx + 0.2) * T
                y0 = (cy + 0.5) * T
                dr.line([(x0, y0), (x0 + 10, y0)], fill=C["water_lt"], width=3)
        else:
            if len(pts) < 2:
                continue
            # 沿水线撒短亮划线, 位置 / 偏移随机 (确定性种子): 不能排成一条
            # 规整虚线, 否则像条航线横在水上。所以划线很稀 (约每 150px
            # 一个)、横向随机偏移 ±14px、方向一律水平, 只是零星波光。
            rnd = random.Random(2000 + wi)
            px = [(x * T, y * T) for x, y in pts]
            acc = 0.0
            for (ax, ay), (bx, by) in zip(px, px[1:]):
                seg = math.hypot(bx - ax, by - ay)
                if seg <= 0:
                    continue
                ux, uy = (bx - ax) / seg, (by - ay) / seg
                nx, ny = -uy, ux  # 法向
                s = 0.0
                while s < seg:
                    if (acc + s) % 150 < 12 and rnd.random() < 0.6:
                        off = rnd.uniform(-14, 14)
                        cx0 = ax + ux * s + nx * off
                        cy0 = ay + uy * s + ny * off
                        dr.line([(cx0 - 6, cy0), (cx0 + 6, cy0)],
                                fill=C["water_lt"], width=3)
                    s += 12
                acc += seg


# ---------------------------------------------------------------------------
#  主入口
# ---------------------------------------------------------------------------
def render_firered_map(grid, building_heights=None, path=None, pois=None,
                       osm=None, bbox=None, output_path=None,
                       start_name="", end_name=""):
    """画一张火红风地图, 返回 PIL Image (output_path 给了就同时存 PNG)。
    grid 为空时抛 ValueError; 其余输入缺失时降级画 (只按网格画, 不报错),
    调用方 (baker) 负责兜底: 渲染失败不能丢 JSON。"""
    if not grid or not grid[0]:
        raise ValueError("render_firered_map: empty grid")
    H, W = len(grid), len(grid[0])
    heights = building_heights or [[0] * W for _ in range(H)]
    path_pts = _norm_path(path)
    walk_pts = [(x, y) for x, y, t in path_pts if t in ("walking", "bicycling")]
    poi_list = _norm_pois(pois)
    tiles = _Tiles()

    # OSM -> 矢量 sidecar (没 bbox 时跳过矢量层, 只按网格画)
    # grid_only: 完全没 OSM 时, 地面按网格自己的格值画 (草画草、路画路),
    # 否则没 OSM landuse 的格子会全变铺装灰、路也看不见 (Mock 就是这么空的)。
    grid_only = not (osm and bbox)
    if osm and bbox:
        roads, water, osm_buildings, ground_grid = _osm_to_sidecars(
            osm, bbox, (W, H))
    else:
        roads, water, osm_buildings, ground_grid = [], [], [], [[0] * W for _ in range(H)]

    def cell(x, y):
        return grid[y][x] if 0 <= x < W and 0 <= y < H else -1

    def is_building(x, y):
        return cell(x, y) == BUILDING

    # ---- 建筑连通块: 一块一个屋顶色、一块一个门 ----
    blob_id = [[-1] * W for _ in range(H)]
    blobs = []
    for _y in range(H):
        for _x in range(W):
            if grid[_y][_x] == BUILDING and blob_id[_y][_x] < 0:
                bid = len(blobs)
                q = deque([(_x, _y)])
                blob_id[_y][_x] = bid
                cells = []
                while q:
                    cx, cy = q.popleft()
                    cells.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < W and 0 <= ny < H
                                and grid[ny][nx] == BUILDING and blob_id[ny][nx] < 0):
                            blob_id[ny][nx] = bid
                            q.append((nx, ny))
                blobs.append(cells)
    door_cell = {}
    for bid, cells in enumerate(blobs):
        cxm = sum(c[0] for c in cells) / len(cells)
        cands = [(x, y) for x, y in cells
                 if not is_building(x, y + 1) and cell(x, y + 1) == ROAD]
        if cands:
            door_cell[bid] = min(cands, key=lambda p: abs(p[0] - cxm))

    # ---- 地标金顶: POI 名含"故宫"/"午门"的楼群画金顶红墙 (名字触发, 非坐标) ----
    palace_pois = [(x, y) for n, x, y, _c in poi_list
                   if "故宫" in n or "午门" in n]
    palace_blobs = set()
    _pal_x0 = _pal_x1 = _pal_y1 = 0
    if palace_pois:
        _pxs = [px for px, _ in palace_pois]
        _pys = [py for _, py in palace_pois]
        _pal_x0, _pal_x1 = min(_pxs) - 15, max(_pxs) + 15
        _pal_y1 = max(_pys) + 15
        for bid, cells in enumerate(blobs):
            in_rect = any(_pal_x0 <= x <= _pal_x1 and 0 <= y <= _pal_y1
                          for x, y in cells)
            near_poi = any(abs(x - px) <= 8 and abs(y - py) <= 8
                           for x, y in cells for px, py in palace_pois)
            mean_y = sum(y for _, y in cells) / len(cells)
            if (in_rect or near_poi) and mean_y <= _pal_y1:
                palace_blobs.add(bid)

    # ---- 地面 (OSM landuse: 有草/广场/停车场/裸土的地方才变, 其余铺装灰) ----
    grass_cells, paved_cells = set(), set()

    def ground_tile(cx, cy):
        g = ground_grid[cy][cx] if 0 <= cy < H and 0 <= cx < W else 0
        if g == 1:
            grass_cells.add((cx, cy))
            return tiles.grass
        if g == 2:
            paved_cells.add((cx, cy))
            return tiles.plaza
        if g == 3:
            paved_cells.add((cx, cy))
            return tiles.parking
        if g == 4:
            paved_cells.add((cx, cy))
            return tiles.dirt
        paved_cells.add((cx, cy))
        return tiles.paved

    # ---- 矢量楼 (描边轮廓 / 屋顶分片 / 烘焙丢楼找回) ----
    traced_blobs, hole_cells, under_cells = trace_large_blobs(
        blobs, blob_id, grid, W, H)
    _recovered = recovered_buildings(osm_buildings, grid, W, H)
    _completion = completion_buildings(osm_buildings, grid, W, H)
    _pieces = roof_pieces(osm_buildings, blob_id, grid, W, H, traced_blobs)

    def _poly_palette(pts, levels):
        """一个 OSM 多边形的屋顶色: 跟它主要重合的网格块取色, 保持一致。"""
        from collections import Counter
        cnt = Counter()
        for (_cx, _cy) in polygon_grid_cells(pts, W, H):
            if grid[_cy][_cx] == BUILDING and blob_id[_cy][_cx] >= 0:
                cnt[blob_id[_cy][_cx]] += 1
        if cnt:
            _b = cnt.most_common(1)[0][0]
            _is_pal = _b in palace_blobs
            _variant = 4 if _is_pal else (blobs[_b][0][0] * 7 + blobs[_b][0][1] * 13) % 4
            _band = max((heights[y][x] for x, y in blobs[_b]), default=1)
            return roof_palette(_variant, max(1, int(_band)), _is_pal), _is_pal
        _cx = sum(p[0] for p in pts) / len(pts)
        _cy = sum(p[1] for p in pts) / len(pts)
        _in_rect = _pal_x0 <= _cx <= _pal_x1 and 0 <= _cy <= _pal_y1
        _near_poi = any(abs(_cx - _px) <= 8 and abs(_cy - _py) <= 8
                        for _px, _py in palace_pois)
        _is_pal = bool(palace_pois) and (_in_rect or _near_poi) and _cy <= _pal_y1
        _variant = 4 if _is_pal else (int(_cx) * 7 + int(_cy) * 13) % 4
        return roof_palette(_variant, max(1, int(levels)), _is_pal), _is_pal

    def _draw_pieces(dr):
        for _bid in sorted(_pieces):
            for _pts, _levels, _shade in _pieces[_bid]:
                _pal, _is_pal = _poly_palette(_pts, _levels)
                _base = tuple(max(0, min(255, v + _shade)) for v in _pal[0])
                draw_roof_piece(dr, _pts, _base, _pal[1], _pal[2], T)

    def _draw_traced(dr):
        for _bid in sorted(traced_blobs):
            _is_pal = _bid in palace_blobs
            _variant = 4 if _is_pal else (blobs[_bid][0][0] * 7 + blobs[_bid][0][1] * 13) % 4
            _band = max((heights[y][x] for x, y in blobs[_bid]), default=1)
            _pal = roof_palette(_variant, max(1, int(_band)), _is_pal)
            for _pts in traced_blobs[_bid]:
                draw_building(dr, _pts, _pal, _is_pal, is_building, T,
                              ridge=_bid not in _pieces)
            if _bid in under_cells:
                _wall = (196, 48, 40) if _is_pal else C["wall"]
                draw_under_patches(dr, under_cells[_bid], set(blobs[_bid]),
                                   _pal[0], _wall, _pal[2], T)

    # ---- 底图: 平铺瓦片 (路/水格先铺地面, 矢量层稍后盖上) ----
    img = Image.new("RGB", (W * T, H * T))
    for y in range(H):
        for x in range(W):
            v = grid[y][x]
            if v == BUILDING and blob_id[y][x] in traced_blobs:
                v = GRASS  # 矢量形状稍后盖
            if v == GRASS:
                if grid_only:
                    # 没 OSM 时按网格画: 草就是草 (不走 ground_tile,
                    # 否则没 landuse 的格子全变铺装灰、整张图只剩米色)。
                    grass_cells.add((x, y))
                    t = tiles.grass
                else:
                    t = ground_tile(x, y)
            elif v == ROAD:
                if grid_only:
                    # 没 OSM 时路按网格画成灰路条, 否则路格和草格一样
                    # 都是铺装灰、红线就飘在空地上 (Mock 原样)。
                    paved_cells.add((x, y))
                    t = tiles.road
                else:
                    t = ground_tile(x, y)
            elif v == BUILDING:
                edges = set()
                if not is_building(x, y - 1):
                    edges.add("N")
                if not is_building(x, y + 1):
                    edges.add("S")
                if not is_building(x - 1, y):
                    edges.add("W")
                if not is_building(x + 1, y):
                    edges.add("E")
                bid = blob_id[y][x]
                is_pal = bid in palace_blobs
                if not is_building(x, y + 1):
                    is_door = door_cell.get(bid) == (x, y)
                    t = tiles.wall(has_door=is_door,
                                   has_window=(x % 2 == 0 and not is_door),
                                   edges=edges, palace=is_pal)
                else:
                    hgt = heights[y][x] if 0 <= y < H and 0 <= x < W else 0
                    variant = 4 if is_pal else (blobs[bid][0][0] * 7 + blobs[bid][0][1] * 13) % 4
                    t = tiles.roof(max(1, int(hgt)), edges, variant=variant,
                                   is_top=not is_building(x, y - 1), seam=(x % 6 == 0))
            elif v == WATER:
                t = ground_tile(x, y)
            elif v == TREE:
                t = tiles.tree
            elif v == SIDEWALK:
                t = tiles.walk
            elif v == POI:
                t = tiles.poi
            elif v == PLAZA:
                paved_cells.add((x, y))
                t = tiles.plaza
            else:
                grass_cells.add((x, y))
                t = tiles.grass
            img.paste(t, (x * T, y * T))

    # 草地 / 铺装整图纹理 (不按格子, 无方格感)
    _apply_texture(img, grass_cells, seed=20261126, strength=0.11)
    _apply_texture(img, paved_cells, seed=20261127, strength=0.055)

    # 矢量楼第一遍 + 庭院 + 屋顶分片
    _vb = ImageDraw.Draw(img)
    _draw_traced(_vb)
    for _bid, _cells in hole_cells.items():
        for _hx, _hy in _cells:
            img.paste(ground_tile(_hx, _hy), (_hx * T, _hy * T))
    _draw_pieces(_vb)

    # 快照 (无水无路的干净图): 小楼 / 湖中岛被矢量水路盖住时从这里恢复
    base_snapshot = img.copy()

    # ---- 水体兜底: 网格水格描边成平滑水面, 围住的陆地从快照恢复 ----
    _wd0 = ImageDraw.Draw(img)
    for _polys, _cells in _water_blobs(grid, W, H):
        for _loop in _polys:
            _wd0.polygon([(x * T, y * T) for x, y in _loop], fill=C["water"])
    for (_hx, _hy) in _enclosed_land_cells(grid, W, H):
        img.paste(base_snapshot.crop((_hx * T, _hy * T,
                                      (_hx + 1) * T, (_hy + 1) * T)),
                  (_hx * T, _hy * T))

    # ---- 矢量水 (OSM 水线 / 水面) + 波光; 多边形内环 (堤/岛) 从快照恢复 ----
    _wd = ImageDraw.Draw(img)
    for wseg in water:
        _pts = [(x * T, y * T) for x, y in wseg["pts"]]
        if wseg["closed"]:
            if len(_pts) >= 3:
                _wd.line(_pts + [_pts[0]], fill=C["water"], width=2 * T, joint="curve")
                _wd.polygon(_pts, fill=C["water"])
                for _hole in wseg.get("holes", []) or []:
                    for (_hx, _hy) in polygon_grid_cells(_hole, W, H):
                        img.paste(base_snapshot.crop((_hx * T, _hy * T,
                                                      (_hx + 1) * T, (_hy + 1) * T)),
                                  (_hx * T, _hy * T))
        else:
            if len(_pts) >= 2:
                _wd.line(_pts, fill=C["water_dk"], width=2 * T + 4, joint="curve")
                _wd.line(_pts, fill=C["water"], width=2 * T, joint="curve")
    _draw_water_sparkles(_wd, water, W, H)

    # ---- 矢量路 (近路线的 + 主干道, 并道, 桥面盖水) ----
    water_lines = []
    for wseg in water:
        wl_pts = list(wseg["pts"])
        if wseg["closed"] and len(wl_pts) >= 3:
            wl_pts = wl_pts + [wl_pts[0]]
        if len(wl_pts) >= 2:
            water_lines.append(wl_pts)
    roads = _merge_parallel_lanes(_keep_roads(roads, walk_pts))
    _rd = ImageDraw.Draw(img)
    for _road in roads:
        if len(_road["pts"]) < 2:
            continue
        _w = max(6, _road["w"] * T)
        _bridge_w = max(_w, 2 * T + 12)
        for _run, _is_bridge in _bridge_runs(_road["pts"], water_lines):
            _pp = [(x * T, y * T) for x, y in _run]
            if len(_pp) < 2:
                continue
            _rw = _bridge_w if _is_bridge else _w
            _rd.line(_pp, fill=C["road_edge"], width=_rw + 4, joint="curve")
            _rd.line(_pp, fill=C["road"], width=_rw, joint="curve")
            if _rw >= 24:
                _dashed(_rd, _pp, C["road_line"], 2)

    # 矢量层漏掉的水格 (OSM 水线没盖到的边角) 平铺补蓝, 楼第二遍会再盖回来。
    # 只补矢量水 2 格以外的格子: 水线本身 2 格宽, 贴线的水格只是线画偏了
    # 半格, 补上去会把平滑的水线包上一圈楼梯边。
    _wmask = Image.new("L", (W, H), 0)
    _wmd = ImageDraw.Draw(_wmask)
    for wseg in water:
        if wseg["closed"]:
            if len(wseg["pts"]) >= 3:
                _wmd.polygon(wseg["pts"], fill=1)
                _wmd.line(wseg["pts"] + [wseg["pts"][0]], fill=1, width=5,
                          joint="curve")
        elif len(wseg["pts"]) >= 2:
            _wmd.line(wseg["pts"], fill=1, width=5, joint="curve")
    _wmpx = _wmask.load()
    for y in range(H):
        for x in range(W):
            if grid[y][x] != WATER or _wmpx[x, y]:
                continue
            cxp, cyp = x * T + T // 2, y * T + T // 2
            r, g, b = img.getpixel((cxp, cyp))
            if abs(r - 56) + abs(g - 118) + abs(b - 214) > 90:
                _rd.rectangle([x * T, y * T, (x + 1) * T - 1, (y + 1) * T - 1],
                              fill=C["water"])

    # ---- 矢量楼第二遍 (路 / 水盖住的楼画回来) ----
    _vb2 = ImageDraw.Draw(img)
    _draw_traced(_vb2)
    for _bid, _cells in enumerate(blobs):
        if _bid in traced_blobs:
            continue
        for (_sx, _sy) in _cells:
            img.paste(base_snapshot.crop((_sx * T, _sy * T,
                                          (_sx + 1) * T, (_sy + 1) * T)),
                      (_sx * T, _sy * T))
    for _bid, _cells in hole_cells.items():
        for _hx, _hy in _cells:
            img.paste(ground_tile(_hx, _hy), (_hx * T, _hy * T))
    _draw_pieces(_vb2)
    for _pts, _levels, _name in _recovered:
        _pal, _is_pal = _poly_palette(_pts, _levels)
        fill_missing_cells(_vb2, _pts, grid, W, H, _pal[0], T)
        draw_building(_vb2, _pts, _pal, _is_pal, is_building, T)
    for _pts, _levels, _name in _completion:
        _pal, _is_pal = _poly_palette(_pts, _levels)
        fill_missing_cells(_vb2, _pts, grid, W, H, _pal[0], T)

    # 小楼南侧阴影
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for y in range(H):
        for x in range(W):
            if (grid[y][x] == BUILDING and blob_id[y][x] not in traced_blobs
                    and not is_building(x, y + 1)):
                gx, gy = x * T, (y + 1) * T
                if cell(x, y + 1) in (GRASS, ROAD, PLAZA, SIDEWALK):
                    od.rectangle([gx, gy, gx + T - 1, gy + 4], fill=(0, 0, 0, 100))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    # ---- 路线红线: 只画步行 / 骑行段, 每段先视线法平滑再画 ----
    if walk_pts:
        runs = []
        cur = [(walk_pts[0][0], walk_pts[0][1])]
        for (x, y, t) in path_pts:
            if t not in ("walking", "bicycling"):
                if len(cur) >= 2:
                    runs.append(cur)
                cur = []
                continue
            if not cur or cur[-1] != (x, y):
                cur.append((x, y))
        if len(cur) >= 2:
            runs.append(cur)
        _odr = ImageDraw.Draw(img)
        for run in runs:
            if len(run) < 2:
                continue
            smoothed = smooth_path_on_grid(
                [{"x": x, "y": y} for x, y in run], grid)
            _route_px = [((p["x"] + 0.5) * T, (p["y"] + 0.5) * T)
                         for p in smoothed]
            if len(_route_px) >= 2:
                _odr.line(_route_px, fill=(255, 255, 255), width=7, joint="curve")
                _odr.line(_route_px, fill=C["route"], width=4, joint="curve")
        # 起 / 终点标记
        _od2 = ImageDraw.Draw(img)
        for ((mx, my), col) in ((walk_pts[0], C["route_start"]),
                                (walk_pts[-1], C["route"])):
            cxp, cyp = (mx + 0.5) * T, (my + 0.5) * T
            _od2.ellipse([cxp - 4, cyp - 4, cxp + 4, cyp + 4],
                         fill=col, outline=(255, 255, 255))

    # ---- 通用标注: 起终点名 + POI 名 (短名、去重、拉开间距, 不写死地名) ----
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for font_path in (FONT_PATH, windows_fonts / "msyh.ttc", windows_fonts / "simhei.ttf"):
        try:
            f_lab = ImageFont.truetype(str(font_path), 22)
            break
        except OSError:
            continue
    else:
        f_lab = ImageFont.load_default()

    label_draw = ImageDraw.Draw(img, "RGBA")

    def map_label(text, gx, gy):
        px, py = (gx + 0.5) * T, (gy + 0.5) * T
        left, top, right, bottom = label_draw.textbbox((0, 0), text, font=f_lab)
        width, height = right - left, bottom - top
        pad_x, pad_y = 6, 3
        margin_x, margin_y = pad_x + 2, pad_y + 2
        if width > img.width - 2 * margin_x or height > img.height - 2 * margin_y:
            return
        x = max(margin_x, min(px - width / 2, img.width - width - margin_x))
        y = max(margin_y, min(py - height / 2, img.height - height - margin_y))
        label_draw.rounded_rectangle((x - pad_x, y - pad_y,
                                      x + width + pad_x, y + height + pad_y),
                                     radius=3, fill=(35, 34, 31, 210))
        label_draw.text((x - left, y - top), text, font=f_lab, fill=(255, 248, 230))

    labelled = []
    if walk_pts and start_name:
        map_label(start_name, walk_pts[0][0], walk_pts[0][1] + 2)
        labelled.append(walk_pts[0])
    if walk_pts and end_name and end_name != start_name:
        map_label(end_name, walk_pts[-1][0], walk_pts[-1][1] + 2)
        labelled.append(walk_pts[-1])
    n_labels = 0
    for name, gx, gy, cat in poi_list:
        if n_labels >= 10:
            continue
        # 只标风景 / 休闲 / 科教 / 公共类 (餐馆商店酒店不标); 没分类的照标
        if cat and cat not in _LABEL_CATEGORIES:
            continue
        # 名字以起 / 终点地名开头的, 去掉前缀再标 ("杭州西湖风景名胜区-子久草堂" -> "子久草堂")
        short = name
        for prefix in (start_name, end_name):
            if prefix and short.startswith(prefix):
                short = short[len(prefix):].lstrip("-·• 　")
                break
        if not short or len(short) > 8:
            continue
        if any(abs(gx - lx) <= 14 and abs(gy - ly) <= 14 for lx, ly in labelled):
            continue
        if short in (start_name, end_name):
            continue
        map_label(short, gx, gy - 6)
        labelled.append((gx, gy))
        n_labels += 1

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, format="PNG")
    return img


__all__ = ["render_firered_map", "T"]
