"""Text 模式: 自然语言日志 -> LLM 拆地点 -> 高德 POI + 路径 -> JSON

Pipeline:
  1. LLM 提取地点 (fallback 正则)
  2. 高德 place_text 搜 POI (城市限定, fallback geocode)
  3. 按距离 + 关键词启发式决定 transport
  4. 高德 route 拿 polyline
  5. 网格化
  6. LLM 生成 weather/mood/dialogs
  7. 时间归一 (t_offset -> 秒)
"""
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from ..core.gridifier import (
    polyline_to_points, points_to_grid, build_grid_from_waypoints,
    compute_bounds, approx_distance_km,
)
from ..core.time_scale import normalize_dialog_times
from ..core.schema import Waypoint, Dialog
from ..clients.amap import AmapClient
from ..clients.llm import LLMClient
from .base import BaseMode

# 关键词命中表
SUBWAY_KW = ("地铁", "公交", "城铁", "BRT", "轻轨")
DRIVE_KW = ("开车", "打车", "驾车", "滴滴", "出租", "的士", "网约车")
BIKE_KW = ("骑车", "自行车", "共享单车", "单车", "摩托", "电动车", "小电驴")


class TextMode(BaseMode):
    def __init__(self, name: str, text: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.text = text
        self.llm = LLMClient(
            api_key=self.config.get("minimax", {}).get("api_key", ""),
            group_id=self.config.get("minimax", {}).get("group_id", ""),
            base_url=self.config.get("minimax", {}).get("base_url", "https://api.minimaxi.com/v1"),
            model=self.config.get("minimax", {}).get("text_model", "MiniMax-Text-01"),
        )
        self.amap = AmapClient(
            api_key=self.config.get("amap", {}).get("api_key", ""),
            base_url=self.config.get("amap", {}).get("base_url", "https://restapi.amap.com/v3"),
        )
        self.default_city = self.config.get("bake", {}).get("default_city", "北京")

    def run(self) -> "LogPayload":
        p = self.payload
        p.meta.title = self.text[:30]
        p.meta.raw_text = self.text

        # 1) 提取地点
        places = self._extract_places()
        if len(places) < 2:
            print(f"[text] 地点数 {len(places)} < 2, 失败: {places}")
            sys.exit(2)
        print(f"[text] 提取地点 ({len(places)} 个): {places}")

        # 2) POI 搜索
        if not self.amap.enabled():
            print("[text] 高德 Key 缺失, 无法 geocode。回 --mock 或 --coords 模式。")
            sys.exit(3)
        geo_results = self._geocode_all(places)
        if len(geo_results) < 2:
            print(f"[text] geocode 成功数 {len(geo_results)} < 2, 失败")
            sys.exit(4)

        # 3 + 4) 调路径
        coords = [(g["lng"], g["lat"]) for g in geo_results]
        all_waypoints_px: List[Tuple[float, float]] = []
        cum_time = 0.0
        waypoint_metas: List[Dict[str, str]] = []

        has_subway = any(kw in self.text for kw in SUBWAY_KW)
        has_drive = any(kw in self.text for kw in DRIVE_KW)
        has_bike = any(kw in self.text for kw in BIKE_KW)

        for i in range(len(coords) - 1):
            approx_km = approx_distance_km(coords[i], coords[i + 1])
            mode = self._pick_transport(approx_km, has_subway, has_drive, has_bike)
            print(f"[text]   {geo_results[i]['name']} -> {geo_results[i + 1]['name']} "
                  f"({approx_km:.1f} km) 用 {mode}")
            route = self.amap.route(coords[i], coords[i + 1], mode=mode)
            if route and route.get("polyline"):
                pts = polyline_to_points(route["polyline"])
                seg_duration = route.get("duration", 60.0)
                all_waypoints_px.extend(pts)
                cum_time += seg_duration
                waypoint_metas.append({"transport": mode, "label": geo_results[i + 1]["name"]})
            else:
                print(f"[text]     {mode} 路径 API 失败, fallback 直线 + walking")
                all_waypoints_px.append(coords[i])
                all_waypoints_px.append(coords[i + 1])
                cum_time += 60.0
                waypoint_metas.append({"transport": "walking", "label": geo_results[i + 1]["name"]})

        # 5) 网格化
        if not all_waypoints_px:
            print("[text] 无有效路径点")
            sys.exit(5)
        bounds = compute_bounds(all_waypoints_px)
        waypoints_grid = points_to_grid(all_waypoints_px, bounds, (p.map.width, p.map.height))
        p.map.grid = build_grid_from_waypoints(waypoints_grid, p.map.width, p.map.height)

        # 6) 组装 waypoint + meta
        n = len(waypoints_grid)
        for i, wp in enumerate(waypoints_grid):
            ratio = i / max(n - 1, 1)
            t = ratio * cum_time
            meta_idx = min(int(ratio * len(waypoint_metas)), len(waypoint_metas) - 1)
            meta = waypoint_metas[meta_idx]
            p.path.append(Waypoint(
                x=wp["x"], y=wp["y"], t=t,
                label=meta.get("label", f"pt_{i}"),
                transport=meta.get("transport", "walking"),
            ))

        # 7) LLM 生成 meta + dialogs
        place_names = [g["name"] for g in geo_results]
        llm_meta = self.llm.generate_meta(self.text, place_names)
        p.meta.weather = llm_meta.get("weather", "unknown")
        p.meta.mood = llm_meta.get("mood", "calm")
        p.meta.bgm = llm_meta.get("bgm", "")
        # dialogs (t_offset -> 秒)
        raw_dialogs = llm_meta.get("dialogs", [])
        normalized = normalize_dialog_times(raw_dialogs, cum_time)
        for d in normalized:
            p.dialogs.append(Dialog(
                t=d.get("t", 0), speaker=d.get("speaker", "Me"), text=d.get("text", "")
            ))

        return p

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------
    def _extract_places(self) -> List[str]:
        places = self.llm.extract_places(self.text)
        if places:
            return places
        # fallback 正则
        print("[text] LLM 不可用, fallback 正则解析")
        parts = re.split(r'[,，、;；]|然后|接着|之后|再|又', self.text)
        out: List[str] = []
        for part in parts:
            for m in re.finditer(r'(?:从|到|在|去|经过)([^,，。;；到从在去]{2,12})', part):
                place = m.group(1).strip()
                if place and len(place) >= 2 and place not in out:
                    out.append(place)
        return out

    def _geocode_all(self, places: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for name in places[:6]:
            # 优先 place_text (适合 POI 简称)
            loc = self.amap.place_text(name, city=self.default_city)
            if loc:
                lng, lat, real_name = loc
                results.append({"name": real_name, "lng": lng, "lat": lat})
                print(f"[text]   {name} -> {real_name} ({lng:.4f}, {lat:.4f}) [{self.default_city}]")
                continue
            # fallback geocode
            loc2 = self.amap.geocode(name, city=self.default_city)
            if loc2:
                results.append({"name": name, "lng": loc2[0], "lat": loc2[1]})
                print(f"[text]   {name} -> ({loc2[0]:.4f}, {loc2[1]:.4f}) [geocode fallback]")
                continue
            print(f"[text]   {name} -> 失败, 跳过")
        return results

    @staticmethod
    def _pick_transport(approx_km: float, has_subway: bool, has_drive: bool, has_bike: bool) -> str:
        """启发式: 关键词优先, 距离兜底"""
        if has_subway and approx_km > 3.0:
            return "transit"
        if has_drive and approx_km > 1.0:
            return "driving"
        if has_bike and approx_km < 10.0:
            return "bicycling"
        if approx_km < 1.0:
            return "walking"
        if approx_km < 5.0:
            return "walking"
        return "driving"
