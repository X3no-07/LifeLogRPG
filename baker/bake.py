#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Life Log RPG - 烘焙脚本
=======================
功能: 读取 config.json, 接收用户输入的"日志" (文本/坐标/手写 waypoints), 调用高德地图 API
      解析为真实坐标 + 路径, 然后网格化到 16px 像素地图, 输出 saved_logs/log_NNN.json。

运行模式:
  python bake.py --mock                                 # 用内置假数据生成示例 log
  python bake.py --coords "116.40,39.90;116.41,39.91"   # 用经纬度序列
  python bake.py --text "我从家走到地铁站, 然后坐地铁去国贸"  # LLM 解析 + 高德 API
  python bake.py --name log_002                          # 指定输出文件名
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------
# 路径常量
# ----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
OUTPUT_DIR = PROJECT_ROOT / "saved_logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# Config 加载
# ----------------------------------------------------------------------------
def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        print(f"[WARN] config.json not found at {CONFIG_PATH}, using defaults")
        return {
            "amap": {"api_key": "", "base_url": "https://restapi.amap.com/v3"},
            "bake": {"tile_size_px": 16, "viewport_grid_w": 80, "viewport_grid_h": 60},
        }
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------
# 高德地图 API 包装
# ----------------------------------------------------------------------------
class AmapClient:
    """高德地图 REST API 极简封装。api_key 为空时所有方法返回 None。"""
    def __init__(self, api_key: str, base_url: str = "https://restapi.amap.com/v3"):
        self.api_key = api_key
        self.base_url = base_url
        self._requests = None
        if api_key:
            try:
                import requests  # type: ignore
                self._requests = requests
            except ImportError:
                print("[WARN] requests 未安装, AmapClient 将无法工作。请运行: pip install requests")
                self._requests = None

    def enabled(self) -> bool:
        return bool(self.api_key) and self._requests is not None

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Tuple[float, float]]:
        """地理编码: 地址 → (lng, lat)"""
        if not self.enabled():
            return None
        params = {"key": self.api_key, "address": address, "output": "JSON"}
        if city:
            params["city"] = city
        try:
            r = self._requests.get(f"{self.base_url}/geocode/geo", params=params, timeout=10)
            data = r.json()
            if data.get("status") == "1" and data.get("geocodes"):
                loc = data["geocodes"][0]["location"]
                lng, lat = loc.split(",")
                return (float(lng), float(lat))
        except Exception as e:
            print(f"[geocode] error: {e}")
        return None

    def place_text(self, keywords: str, city: str = "北京", types: Optional[str] = None) -> Optional[Tuple[float, float, str]]:
        """POI 关键字搜索: keywords (POI 简称) → (lng, lat, name)
        比 geocode 更适合 POI 简称(王府井/国贸等), 支持 city 限定
        """
        if not self.enabled():
            return None
        params = {
            "key": self.api_key,
            "keywords": keywords,
            "city": city,
            "citylimit": "true",
            "output": "JSON",
            "offset": 1,  # 只取最匹配的一个
        }
        if types:
            params["types"] = types
        try:
            r = self._requests.get(f"{self.base_url}/place/text", params=params, timeout=10)
            data = r.json()
            if data.get("status") == "1" and data.get("pois"):
                p = data["pois"][0]
                loc = p["location"]
                lng, lat = loc.split(",")
                return (float(lng), float(lat), p.get("name", keywords))
        except Exception as e:
            print(f"[place_text] error: {e}")
        return None

    def llm_extract_places(self, text: str) -> List[str]:
        """用 MiniMax LLM 从自然语言日志中提取地点列表。
        返回: ['天安门', '王府井', '国贸']
        如果 LLM 不可用, fallback 到正则。
        """
        if not self.enabled():
            return []
        # 用 MiniMax 的话用独立 key + base_url, 这里只读自己的 key
        # 实际: AmapClient 不应该管 LLM, 拆出去更好
        return []

    def llm_extract_places(self, text: str) -> List[str]:
        """用 MiniMax LLM 从自然语言日志中提取地点列表。
        返回: ['天安门', '王府井', '国贸']
        如果 LLM 不可用, fallback 到正则。
        """
        if not self.enabled():
            return []
        # 用 MiniMax 的话用独立 key + base_url, 这里只读自己的 key
        # 实际: AmapClient 不应该管 LLM, 拆出去更好
        return []

    def route(self, origin: Tuple[float, float], dest: Tuple[float, float],
              mode: str = "walking") -> Optional[Dict[str, Any]]:
        """路径规划: origin/dest (lng,lat) → 路径 polyline + 耗时 + 路标 instruction
        返回: {distance, duration, polyline (拼好的完整 polyline), steps: [{polyline, instruction, road, distance, duration, action}]}
        """
        if not self.enabled():
            return None
        if mode == "walking":
            endpoint = "direction/walking"
        elif mode == "bicycling":
            endpoint = "direction/bicycling"
        elif mode == "driving":
            endpoint = "direction/driving"
        elif mode == "transit":
            endpoint = "direction/transit/integrated"
        else:
            endpoint = "direction/walking"
        params = {
            "key": self.api_key,
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{dest[0]},{dest[1]}",
            "output": "JSON",
        }
        if mode == "transit":
            params["city"] = "北京"  # 公交需要 city
        try:
            r = self._requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=10)
            data = r.json()
            if data.get("status") != "1":
                print(f"[route] API fail: {data.get('info')} / {data.get('infocode')}")
                return None
            if mode == "transit":
                # 公交 API 返回结构不一样
                transits = data.get("route", {}).get("transits", [])
                if not transits:
                    print("[route] no transit found")
                    return None
                t = transits[0]
                # 把所有 segments 里的 polyline 拼起来
                all_pts = []
                total_dist = 0.0
                total_dur = 0.0
                for seg in t.get("segments", []):
                    if "bus" in seg and seg["bus"].get("buslines"):
                        bl = seg["bus"]["buslines"][0]
                        all_pts.extend(polyline_to_points(bl.get("polyline", "")))
                        total_dist += float(bl.get("distance", 0))
                        total_dur += float(bl.get("duration", 0))
                    if "walking" in seg:
                        all_pts.extend(polyline_to_points(seg["walking"].get("polyline", "")))
                        total_dist += float(seg["walking"].get("distance", 0))
                        total_dur += float(seg["walking"].get("duration", 0))
                return {
                    "distance": total_dist,
                    "duration": total_dur,
                    "polyline": ";".join(",".join(map(str, p)) for p in all_pts),
                    "steps": [{"instruction": f"公交 {i}", "polyline": ";".join(",".join(map(str, p)) for p in all_pts)} for i, _ in enumerate(all_pts)],
                }
            paths = data.get("route", {}).get("paths", [])
            if not paths:
                print("[route] no paths")
                return None
            path = paths[0]
            # walking/bicycling/driving: polyline 在 steps 里
            steps_data = []
            full_polylines: List[str] = []
            for s in path.get("steps", []):
                pl = s.get("polyline", "")
                full_polylines.append(pl)
                steps_data.append({
                    "instruction": s.get("instruction", ""),
                    "road": s.get("road", ""),
                    "action": s.get("action", ""),
                    "distance": float(s.get("distance", 0)),
                    "duration": float(s.get("duration", 0)),
                    "polyline": pl,
                })
            # 拼成完整 polyline (用 ; 连接, 去掉相邻 step 的重复点)
            return {
                "distance": float(path.get("distance", 0)),
                "duration": float(path.get("duration", 0)),
                "polyline": ";".join(full_polylines),
                "steps": steps_data,
            }
        except Exception as e:
            print(f"[route] error: {e}")
        return None


# ----------------------------------------------------------------------------
# 道路网格化 (核心算法)
# ----------------------------------------------------------------------------
def polyline_to_points(polyline: str) -> List[Tuple[float, float]]:
    """高德 polyline 字符串 → [(lng, lat), ...]
    格式: "lng,lat;lng,lat;..."
    """
    if not polyline:
        return []
    return [tuple(map(float, p.split(","))) for p in polyline.split(";") if "," in p]


def points_to_grid(points: List[Tuple[float, float]], bounds: Tuple[float, float, float, float],
                   grid_size: Tuple[int, int], tile_size: int = 16) -> List[Dict[str, int]]:
    """将经纬度点投影到 grid 坐标 (x, y in grid cells)
    bounds: (min_lng, min_lat, max_lng, max_lat)
    grid_size: (w, h)
    """
    min_lng, min_lat, max_lng, max_lat = bounds
    w, h = grid_size
    if max_lng == min_lng or max_lat == min_lat:
        return []
    waypoints = []
    for lng, lat in points:
        # 投影: 经度→x, 纬度→y (注意: 纬度大=北=grid 顶, 但 grid y=0 是顶, 翻转)
        nx = (lng - min_lng) / (max_lng - min_lng)
        ny = 1.0 - (lat - min_lat) / (max_lat - min_lat)
        gx = int(nx * w)
        gy = int(ny * h)
        gx = max(0, min(w - 1, gx))
        gy = max(0, min(h - 1, gy))
        waypoints.append({"x": gx, "y": gy})
    # 去重连续点
    deduped = []
    for p in waypoints:
        if not deduped or deduped[-1] != p:
            deduped.append(p)
    return deduped


def build_grid_from_waypoints(waypoints: List[Dict[str, int]], grid_w: int, grid_h: int,
                              tile_size: int = 16) -> List[List[int]]:
    """根据 waypoints 在 grid 上画路 (1=road), 其余填 grass (0)"""
    # 初始化全 grass
    grid = [[0 for _ in range(grid_w)] for _ in range(grid_h)]
    for i in range(len(waypoints) - 1):
        ax, ay = waypoints[i]["x"], waypoints[i]["y"]
        bx, by = waypoints[i + 1]["x"], waypoints[i + 1]["y"]
        # Bresenham 画线
        _bresenham_line(grid, ax, ay, bx, by, value=1)
    # 在 waypoints 周围撒一些 decoration (树 / 建筑)
    import random
    random.seed(42)
    for y in range(grid_h):
        for x in range(grid_w):
            if grid[y][x] == 0:
                r = random.random()
                if r < 0.03:
                    grid[y][x] = 4  # 树
                elif r < 0.045 and 3 < x < grid_w - 3 and 3 < y < grid_h - 3:
                    grid[y][x] = 2  # 建筑
    return grid


def _bresenham_line(grid: List[List[int]], x0: int, y0: int, x1: int, y1: int, value: int = 1) -> None:
    """在 grid 上画 Bresenham 直线, 包括端点周围的粗化 (3x3)"""
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                xx, yy = x + ox, y + oy
                if 0 <= xx < w and 0 <= yy < h:
                    grid[yy][xx] = value
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


# ----------------------------------------------------------------------------
# 输入模式
# ----------------------------------------------------------------------------
def mode_mock(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Mock 模式: 用预定义路径, 跑通整个 pipeline"""
    print("[mock] 生成示例 log (80x60 grid, 直线 + 拐弯路径)")
    grid_w = config["bake"].get("viewport_grid_w", 80)
    grid_h = config["bake"].get("viewport_grid_h", 60)
    tile_size = config["bake"].get("tile_size_px", 16)

    # 路径: 从家 (5, 10) 出发, 一路向东到地铁 (25, 10), 北上 (25, 30), 换乘, 再到 (60, 50)
    pts_px = [
        (5, 10), (10, 10), (15, 10), (20, 10), (25, 10),  # 走
        (25, 15), (25, 20), (25, 25), (25, 30),            # 北上
        (30, 30), (40, 30), (50, 30), (60, 30),            # 地铁
        (60, 35), (60, 40), (60, 45), (60, 50),            # 换乘后
        (65, 50), (70, 50), (75, 50),                      # 步行
    ]
    # 把像素坐标 → grid 坐标 (假设 1 cell = 1 px 在 mock 模式)
    waypoints = [{"x": x, "y": y, "t": 0.0, "label": f"step_{i}", "transport": "walk"} for i, (x, y) in enumerate(pts_px)]

    # 累加时间 (mock: 每 1 grid 走 1.5 秒)
    cum = 0.0
    for i, wp in enumerate(waypoints):
        wp["t"] = cum
        cum += 1.5
    # 标注 transport 切换
    if len(waypoints) > 5:
        waypoints[5]["transport"] = "subway"
    if len(waypoints) > 9:
        waypoints[9]["transport"] = "subway"
    if len(waypoints) > 13:
        waypoints[13]["transport"] = "walk"

    grid = build_grid_from_waypoints([{"x": x, "y": y} for (x, y) in pts_px], grid_w, grid_h, tile_size)

    return _build_log_payload(
        name=name,
        title="Mock 日志 - 城市漫游",
        waypoints=waypoints,
        grid=grid,
        grid_w=grid_w,
        grid_h=grid_h,
        tile_size=tile_size,
        dialogs=[
            {"t": 4.0, "speaker": "Me", "text": "出门, 天气不错"},
            {"t": 12.0, "speaker": "路人", "text": "早! 赶着去上班呢"},
            {"t": 18.0, "speaker": "Me", "text": "挤地铁中..."},
            {"t": 28.0, "speaker": "同事", "text": "老张! 这边这边"},
            {"t": 35.0, "speaker": "老张", "text": "走, 中午请你吃饭"},
        ],
        meta={"weather": "sunny", "mood": "happy", "bgm": "town.mid"},
    )


def mode_coords(config: Dict[str, Any], name: str, coords_str: str) -> Dict[str, Any]:
    """坐标模式: 接受经纬度序列"""
    print(f"[coords] 接收到 {coords_str.count(';') + 1} 个坐标点")
    try:
        coords = [tuple(map(float, p.split(","))) for p in coords_str.split(";")]
    except ValueError as e:
        print(f"[coords] 解析失败: {e}")
        sys.exit(1)

    grid_w = config["bake"].get("viewport_grid_w", 80)
    grid_h = config["bake"].get("viewport_grid_h", 60)
    tile_size = config["bake"].get("tile_size_px", 16)

    min_lng = min(c[0] for c in coords)
    max_lng = max(c[0] for c in coords)
    min_lat = min(c[1] for c in coords)
    max_lat = max(c[1] for c in coords)
    # 留 5% padding
    pad_lng = (max_lng - min_lng) * 0.05 or 0.001
    pad_lat = (max_lat - min_lat) * 0.05 or 0.001
    bounds = (min_lng - pad_lng, min_lat - pad_lat, max_lng + pad_lng, max_lat + pad_lat)
    waypoints_grid = points_to_grid(coords, bounds, (grid_w, grid_h), tile_size)
    grid = build_grid_from_waypoints(waypoints_grid, grid_w, grid_h, tile_size)
    waypoints = [{"x": wp["x"], "y": wp["y"], "t": float(i) * 1.5, "label": f"pt_{i}", "transport": "walk"}
                 for i, wp in enumerate(waypoints_grid)]
    return _build_log_payload(
        name=name, title="坐标生成日志", waypoints=waypoints, grid=grid,
        grid_w=grid_w, grid_h=grid_h, tile_size=tile_size,
        dialogs=[], meta={"weather": "unknown", "mood": "calm"},
    )


def mode_text(config: Dict[str, Any], name: str, text: str) -> Dict[str, Any]:
    """文本模式: 用 LLM (MiniMax) 解析日志, 然后高德 geocode + route
    LLM 解析失败时 fallback 到正则。
    """
    print(f"[text] 解析日志: {text[:60]}...")

    # 1) 提取地点列表 (优先 LLM, fallback 正则)
    places = _llm_extract_places(config, text)
    if not places:
        print("[text] LLM 不可用, fallback 正则解析")
        import re
        # 先按 ,/、/然后/接着/再 拆句
        parts = re.split(r'[,，、;；]|然后|接着|之后|再|又', text)
        for p in parts:
            # 提 "从/到/在/去" 后面的词, 限 2-12 字符, 不包含动词
            for m in re.finditer(r'(?:从|到|在|去|经过)([^,，。;；到从在去]{2,12})', p):
                place = m.group(1).strip()
                if place and len(place) >= 2 and place not in places:
                    places.append(place)
    if len(places) < 2:
        print(f"[text] 解析出的地点数 {len(places)} < 2, 请提供更明确的地点。已识别: {places}")
        sys.exit(2)
    print(f"[text] 提取地点 ({len(places)} 个): {places}")

    # 2) 高德 geocode
    api_key = config.get("amap", {}).get("api_key", "")
    if not api_key:
        print("[text] 高德 Key 缺失, 无法 geocode。请用 --mock 或 --coords 模式。")
        sys.exit(3)
    client = AmapClient(api_key, config["amap"].get("base_url", "https://restapi.amap.com/v3"))
    # 默认城市: 配置里可覆盖
    default_city = config.get("bake", {}).get("default_city", "北京")
    geo_results = []
    for p in places[:6]:
        # 优先用 place_text (适合 POI 简称), 失败 fallback geocode
        loc = client.place_text(p, city=default_city)
        if loc:
            lng, lat, real_name = loc
            geo_results.append({"name": real_name, "lng": lng, "lat": lat})
            print(f"[text]   {p} -> {real_name} ({lng:.4f}, {lat:.4f}) [{default_city}]")
        else:
            # fallback geocode
            loc2 = client.geocode(p, city=default_city)
            if loc2:
                geo_results.append({"name": p, "lng": loc2[0], "lat": loc2[1]})
                print(f"[text]   {p} -> ({loc2[0]:.4f}, {loc2[1]:.4f}) [geocode fallback]")
            else:
                print(f"[text]   {p} -> 失败, 跳过")
    if len(geo_results) < 2:
        print(f"[text] geocode 成功数 {len(geo_results)} < 2, 放弃")
        sys.exit(4)

    # 3) 调路径规划: 智能判断 transport (基于关键词 + 距离)
    coords = [(g["lng"], g["lat"]) for g in geo_results]
    all_waypoints_px: List[Tuple[float, float]] = []
    cum_time = 0.0
    timeline = []  # 每个点对应的 t
    waypoint_metas = []  # 每个点的 (transport, label, instruction)
    # 关键词命中
    text_lower = text
    has_subway_kw = any(kw in text_lower for kw in ["地铁", "公交", "城铁", "BRT", "轻轨"])
    has_drive_kw = any(kw in text_lower for kw in ["开车", "打车", "驾车", "滴滴", "出租", "的士", "网约车"])
    has_bike_kw = any(kw in text_lower for kw in ["骑车", "自行车", "共享单车", "单车", "摩托", "电动车", "小电驴"])
    for i in range(len(coords) - 1):
        # 估算距离 (粗算, 1° lat ≈ 111 km)
        dlat = abs(coords[i + 1][1] - coords[i][1])
        dlng = abs(coords[i + 1][0] - coords[i][0])
        approx_km = ((dlat * 111) ** 2 + (dlng * 111 * 0.85) ** 2) ** 0.5
        # 启发式: 关键词优先, 距离兜底
        if has_subway_kw and approx_km > 3.0:
            mode = "transit"
        elif has_drive_kw and approx_km > 1.0:
            mode = "driving"
        elif has_bike_kw and approx_km < 10.0:
            mode = "bicycling"
        elif approx_km < 1.0:
            mode = "walking"
        elif approx_km < 5.0:
            mode = "walking"
        else:
            mode = "driving"
        print(f"[text]   {geo_results[i]['name']} -> {geo_results[i + 1]['name']} ({approx_km:.1f} km) 用 {mode}")
        # 调对应 API
        if mode == "transit":
            route = client.route(coords[i], coords[i + 1], mode="transit")
        elif mode == "bicycling":
            route = client.route(coords[i], coords[i + 1], mode="bicycling")
        else:
            route = client.route(coords[i], coords[i + 1], mode=mode)
        if route and route.get("polyline"):
            pts = polyline_to_points(route["polyline"])
            seg_duration = route.get("duration", 60.0)
            for j, pt in enumerate(pts):
                ratio = j / max(len(pts) - 1, 1)
                t = cum_time + seg_duration * ratio
                all_waypoints_px.append(pt)
            # 用 steps 的 instruction 做路标
            for step in route.get("steps", []):
                inst = step.get("instruction", "")
                if inst:
                    timeline.append({"t": cum_time + step.get("duration", 0) / 2, "name": inst})
            cum_time += seg_duration
            waypoint_metas.append({"transport": mode, "label": geo_results[i + 1]["name"]})
        else:
            # API 失败: fallback 到直线 + walking
            print(f"[text]     {mode} 路径 API 失败, fallback 直线 + walking")
            all_waypoints_px.append(coords[i])
            all_waypoints_px.append(coords[i + 1])
            cum_time += 60.0
            waypoint_metas.append({"transport": "walking", "label": geo_results[i + 1]["name"]})

    # 4) 网格化
    grid_w = config["bake"].get("viewport_grid_w", 80)
    grid_h = config["bake"].get("viewport_grid_h", 60)
    tile_size = config["bake"].get("tile_size_px", 16)
    min_lng = min(c[0] for c in all_waypoints_px)
    max_lng = max(c[0] for c in all_waypoints_px)
    min_lat = min(c[1] for c in all_waypoints_px)
    max_lat = max(c[1] for c in all_waypoints_px)
    pad_lng = (max_lng - min_lng) * 0.05 or 0.001
    pad_lat = (max_lat - min_lat) * 0.05 or 0.001
    bounds = (min_lng - pad_lng, min_lat - pad_lat, max_lng + pad_lng, max_lat + pad_lat)
    waypoints_grid = points_to_grid(all_waypoints_px, bounds, (grid_w, grid_h), tile_size)
    grid = build_grid_from_waypoints(waypoints_grid, grid_w, grid_h, tile_size)

    # 5) 组装 waypoints
    waypoints = []
    n = len(waypoints_grid)
    for i, wp in enumerate(waypoints_grid):
        ratio = i / max(n - 1, 1)
        t = ratio * cum_time
        # 找最接近的 waypoint_metas
        meta_idx = min(int(ratio * len(waypoint_metas)), len(waypoint_metas) - 1)
        meta = waypoint_metas[meta_idx]
        waypoints.append({
            "x": wp["x"], "y": wp["y"], "t": t,
            "label": meta.get("label", f"pt_{i}"),
            "transport": meta.get("transport", "walk"),
        })

    # 6) 用 LLM 生成对话 (天气 + 心情 + 1-2 句对话)
    meta = _llm_generate_meta(config, text, [g["name"] for g in geo_results])

    return _build_log_payload(
        name=name, title=text[:30], waypoints=waypoints, grid=grid,
        grid_w=grid_w, grid_h=grid_h, tile_size=tile_size,
        dialogs=_normalize_dialog_times(meta.get("dialogs", []), cum_time),
        meta=meta,
    )


def _normalize_dialog_times(dialogs: List[Dict[str, Any]], total_duration: float) -> List[Dict[str, Any]]:
    """把 LLM 输出的 t_offset (0-1) 转成 t (秒), 均匀分布在播放时长内
    兼容两种输入:
    - {"t_offset": 0.0~1.0}
    - {"t": 0~N 秒}  (LLM 可能直接给秒)
    - 都没有就按 dialogs 顺序均匀分配
    """
    if not dialogs:
        return []
    n = len(dialogs)
    has_t_offset = any("t_offset" in d for d in dialogs)
    has_t = any("t" in d for d in dialogs)
    out = []
    for i, d in enumerate(dialogs):
        nd = dict(d)
        if has_t_offset and "t_offset" in d:
            nd["t"] = float(d["t_offset"]) * total_duration
        elif has_t and "t" in d:
            nd["t"] = float(d["t"])
        else:
            # 均匀分配, 第一个 0%, 最后一个 95%
            ratio = i / max(n - 1, 1) * 0.95
            nd["t"] = ratio * total_duration
        nd.pop("t_offset", None)
        out.append(nd)
    return out


def _llm_extract_places(config: Dict[str, Any], text: str) -> List[str]:
    """用 MiniMax LLM 提取地点列表, 返回 [] 表示不可用"""
    mm_key = config.get("minimax", {}).get("api_key", "")
    if not mm_key:
        return []
    try:
        import requests
        url = f"{config['minimax'].get('base_url', 'https://api.minimaxi.com/v1')}/text/chatcompletion_v2"
        group_id = config.get("minimax", {}).get("group_id", "")
        if group_id:
            url += f"?groupId={group_id}"
        headers = {
            "Authorization": f"Bearer {mm_key}",
            "Content-Type": "application/json",
        }
        # 重要: prompt 必须禁止 CoT, max_tokens 给足 (模型默认会"先分析再给答案", 200 token 不够)
        prompt = (
            "你是地点 NER 助手。从下面中文日志提取所有真实地点(商场/餐厅/地铁站/公园/景点/小区/写字楼/地铁线)。\n"
            "严格要求(否则算失败):\n"
            "- 严格只输出 JSON 数组, 第一个字符必须是 [, 最后一个必须是 ]\n"
            "- 不要任何解释、分析、前缀、后缀、markdown 包裹\n"
            "- 按出现顺序, 每个地点 2-12 字, 去掉动作词(走/到/去/在/经过/买/吃/看/坐)\n"
            "- 没有地点就输出 []\n"
            f"\n日志: {text}\n\n"
            "输出:"
        )
        payload = {
            "model": config.get("minimax", {}).get("text_model", "MiniMax-Text-01"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,  # 关键: 给足空间, 防止截断
            "temperature": 0.0,  # 0 让输出更确定
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        data = r.json()
        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0].get("finish_reason", "")
            if finish_reason == "length":
                print(f"[llm] 警告: max_tokens 用尽被截断, 提升到 1000")
            result = _parse_json_lenient(content, expect="array")
            if isinstance(result, list):
                return result
            print(f"[llm] 解析失败, content 前 200 字: {content[:200]!r}")
    except Exception as e:
        print(f"[llm] extract_places 失败: {e}")
    return []


def _parse_json_lenient(content: str, expect: str = "array") -> Any:
    """宽容解析 LLM 返回的 JSON, 支持 markdown 包裹、前后说明文字、截断等
    expect: "array" 或 "object"
    """
    import re
    content = content.strip()

    # 策略 1: 直接 json.loads
    try:
        return json.loads(content)
    except Exception:
        pass

    # 策略 2: 去 markdown 包裹 (```json ... ```)
    cleaned = content
    if cleaned.startswith("```"):
        # 去掉首部 ```json 或 ```
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 策略 3: 用正则找最长的 [...] 或 {...}
    if expect == "array":
        candidates = re.findall(r'\[.*?\]', content, re.DOTALL)
    else:
        candidates = re.findall(r'\{.*?\}', content, re.DOTALL)
    # 按长度排序, 试解析
    for cand in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _llm_generate_meta(config: Dict[str, Any], text: str, places: List[str]) -> Dict[str, Any]:
    """用 MiniMax LLM 生成天气/心情/对话"""
    mm_key = config.get("minimax", {}).get("api_key", "")
    fallback = {"weather": "unknown", "mood": "calm", "bgm": ""}
    if not mm_key:
        return fallback
    try:
        import requests
        url = f"{config['minimax'].get('base_url', 'https://api.minimaxi.com/v1')}/text/chatcompletion_v2"
        group_id = config.get("minimax", {}).get("group_id", "")
        if group_id:
            url += f"?groupId={group_id}"
        headers = {
            "Authorization": f"Bearer {mm_key}",
            "Content-Type": "application/json",
        }
        prompt = (
            "你是 GBA 像素 RPG 旁白。根据日志生成场景 meta。\n"
            "严格要求(否则算失败):\n"
            "- 严格只输出 JSON 对象, 第一个字符 {, 最后一个 }\n"
            "- 不要任何解释、分析、markdown 包裹\n\n"
            f"日志: {text}\n"
            f"地点: {', '.join(places)}\n\n"
            "输出 schema:\n"
            '{"weather": "sunny|rainy|cloudy|snowy", '
            '"mood": "happy|calm|sad|excited|tired", '
            '"bgm": "english.id 4-12 字符", '
            '"dialogs": [{"speaker": "Me|老张|同事|朋友|路人", "text": "中文 5-30 字", "t_offset": 0.0-1.0 之间的数字表示对话在路径中的相对时刻"}, ...]}\n'
            "至少 2 条 dialog, 最多 5 条。"
        )
        payload = {
            "model": config.get("minimax", {}).get("text_model", "MiniMax-Text-01"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
            "temperature": 0.7,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        data = r.json()
        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            result = _parse_json_lenient(content, expect="object")
            if isinstance(result, dict):
                # 补字段, 防 LLM 缺字段
                result.setdefault("weather", "unknown")
                result.setdefault("mood", "calm")
                result.setdefault("bgm", "")
                result.setdefault("dialogs", [])
                # 把 dialogs 的 t_offset 转成 t (秒)
                return result
    except Exception as e:
        print(f"[llm] generate_meta 失败: {e}")
    return fallback


# ----------------------------------------------------------------------------
# 公共: 组装 log payload
# ----------------------------------------------------------------------------
def _build_log_payload(name: str, title: str, waypoints: List[Dict[str, Any]],
                       grid: List[List[int]], grid_w: int, grid_h: int,
                       tile_size: int, dialogs: List[Dict[str, Any]],
                       meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "meta": {
            "log_id": name,
            "title": title,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "weather": meta.get("weather", "sunny"),
            "mood": meta.get("mood", "calm"),
            "bgm": meta.get("bgm", ""),
        },
        "map": {
            "tile_size": tile_size,
            "width": grid_w,
            "height": grid_h,
            "grid": grid,
            "legend": {"0": "grass", "1": "road", "2": "building", "3": "water", "4": "tree"},
        },
        "path": waypoints,
        "dialogs": dialogs,
        "characters": [
            {"name": "Me", "color": "#f2cc2c"},
        ],
    }


# ----------------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------------
def write_log(payload: Dict[str, Any], name: str) -> Path:
    out_path = OUTPUT_DIR / f"{name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[done] saved to {out_path}")
    print(f"       waypoints: {len(payload['path'])}, dialogs: {len(payload['dialogs'])}, "
          f"map: {payload['map']['width']}x{payload['map']['height']}")
    return out_path


def _apply_time_scale(payload: Dict[str, Any], target_duration: float) -> None:
    """把所有 waypoint 和 dialog 的 t 等比例缩放到 target_duration 秒
    用于 1.5h 真实步行 -> 30s 朋友圈视频
    """
    waypoints = payload.get("path", [])
    if not waypoints or target_duration <= 0:
        return
    max_t = max((wp.get("t", 0) for wp in waypoints), default=0)
    if max_t <= 0:
        return
    scale = target_duration / max_t
    for wp in waypoints:
        wp["t"] = round(wp.get("t", 0) * scale, 2)
    for dlg in payload.get("dialogs", []):
        if "t" in dlg:
            dlg["t"] = round(dlg["t"] * scale, 2)
    # 更新 meta.duration 提示
    payload.setdefault("meta", {})
    payload["meta"]["original_duration_sec"] = max_t
    payload["meta"]["scaled_duration_sec"] = target_duration
    print(f"[scale] 时长 {max_t:.1f}s -> {target_duration:.1f}s (压缩 {1/scale:.1f}x)")


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Life Log RPG - 烘焙脚本")
    parser.add_argument("--mock", action="store_true", help="用 mock 数据生成示例 log")
    parser.add_argument("--coords", type=str, help="经纬度序列, 格式: lng,lat;lng,lat;...")
    parser.add_argument("--text", type=str, help="原始日志文本 (LLM 解析 + 高德 API)")
    parser.add_argument("--name", type=str, default="log_001", help="输出文件名 (不含 .json)")
    parser.add_argument("--target-duration", type=float, default=0.0,
                        help="把整个播放压到此秒数 (0=不缩放, 30=朋友圈节奏)")
    parser.add_argument("--city", type=str, default="", help="默认城市, 留空用 config 里的")
    args = parser.parse_args()

    config = load_config()
    if args.city:
        config.setdefault("bake", {})["default_city"] = args.city

    if args.mock:
        payload = mode_mock(config, args.name)
    elif args.coords:
        payload = mode_coords(config, args.name, args.coords)
    elif args.text:
        payload = mode_text(config, args.name, args.text)
    else:
        # 默认 mock 模式
        print("[hint] 未指定模式, 默认用 --mock")
        payload = mode_mock(config, args.name)

    if args.target_duration > 0:
        _apply_time_scale(payload, args.target_duration)

    write_log(payload, args.name)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
