"""Text 模式: 自然语言日志 -> LLM 拆地点 -> 高德 POI + 路径 -> 真实地图

Pipeline:
  1. 提取原文地点，优先识别明确的「从…到…」
  2. 在指定城市确认 POI，完整门牌可用地理编码
  3. 按距离 + 关键词启发式决定 transport
  4. 高德 route 拿 polyline
  5. 切片: path bbox + 800m 半径
  6. OSM Overpass 拉路网/建筑/水系/绿化
  7. 网格化: OSM way -> grid
  8. LLM 生成 weather/mood/dialogs
  9. 时间归一 (t_offset -> 秒)
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from ..core.gridifier import (
    polyline_to_points, build_grid_from_waypoints,
    approx_distance_km, osm_to_grid, densify_and_snap_route,
    route_along_roads, apply_path_overlay, carve_route_passages,
    smooth_path_on_grid, project_walking_track,
)
from ..core.gcj02 import gcj02_to_wgs84, wgs84_to_gcj02, gcj02_to_wgs84_points
from ..core.tiling import slice_around_path, lnglat_to_grid_cell
from ..core.time_scale import normalize_dialog_times
from ..core.stops import build_stops
from ..core.schema import Waypoint, Dialog, POI, TransitMarker, InteriorSlot
from ..clients.amap import AmapClient
from ..clients.llm import LLMClient
from ..clients.osm import OsmClient, parse_overpass
from .base import BaseMode

# 关键词命中表
SUBWAY_KW = ("地铁", "公交", "城铁", "BRT", "轻轨")
DRIVE_KW = ("开车", "打车", "驾车", "滴滴", "出租", "的士", "网约车")
BIKE_KW = ("骑车", "自行车", "共享单车", "单车", "摩托", "电动车", "小电驴")

# POI 分类 (按高德 type 第一段)
POI_CATEGORY = {
    "餐饮服务": "food",
    "购物服务": "shop",
    "生活服务": "life",
    "体育休闲服务": "leisure",
    "医疗保健服务": "medical",
    "住宿服务": "hotel",
    "风景名胜": "scenic",
    "交通设施服务": "transport",
    "政府机构及社会团体": "gov",
    "科教文化服务": "edu",
    "金融保险服务": "finance",
    "公司企业": "company",
    "公共设施": "public",
    "其他": "other",
}


class PlaceResolutionError(Exception):
    """日记里的地点无法唯一定位。"""


class TextMode(BaseMode):
    def __init__(self, name: str, text: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.text = text
        # LLM provider 由 bake.llm_provider 选 ("deepseek" / "minimax"), 默认 deepseek;
        # 每个 provider 读自己那节的 api_key / base_url / text_model, MiniMax 的路保留
        self.llm_provider = self.config.get("bake", {}).get("llm_provider", "deepseek")
        if self.llm_provider == "deepseek":
            _llm_cfg = self.config.get("deepseek", {})
            self.llm = LLMClient(
                api_key=_llm_cfg.get("api_key", ""),
                base_url=_llm_cfg.get("base_url", "https://api.deepseek.com/v1"),
                model=_llm_cfg.get("text_model", "deepseek-chat"),
                timeout=_llm_cfg.get("timeout_sec", 30),
                provider="deepseek",
            )
        else:
            _llm_cfg = self.config.get("minimax", {})
            self.llm = LLMClient(
                api_key=_llm_cfg.get("api_key", ""),
                group_id=_llm_cfg.get("group_id", ""),
                base_url=_llm_cfg.get("base_url", "https://api.minimaxi.com/v1"),
                model=_llm_cfg.get("text_model", "MiniMax-M3.1-Flash"),
                timeout=_llm_cfg.get("timeout_sec", 30),
                provider="minimax",
            )
        amap_config = self.config.get("amap", {})
        self.amap = AmapClient(
            api_key=amap_config.get("api_key", ""),
            base_url=amap_config.get("base_url", "https://restapi.amap.com/v3"),
            timeout=amap_config.get("timeout_sec", 10),
        )
        bake_config = self.config.get("bake", {})
        self.osm = OsmClient(timeout=int(bake_config.get("osm_timeout_sec", 30)))
        self.default_city = bake_config.get("default_city", "北京")
        self.tile_radius_m = int(bake_config.get("tile_radius_m", 800))
        self.fuzzy_candidate_limit = max(0, int(bake_config.get("fuzzy_candidate_limit", 80)))
        self.selected_places: List[Dict[str, Any]] = []

    def run(self) -> "LogPayload":
        p = self.payload
        p.meta.title = self.text[:30]
        p.meta.raw_text = self.text

        # 1) 提取地点
        places = [place["name"] for place in self.selected_places] if self.selected_places else self._extract_places()
        if len(places) < 2:
            print(f"[text] 地点数 {len(places)} < 2, 失败: {places}")
            sys.exit(2)
        print(f"[text] 提取地点 ({len(places)} 个): {places}")

        # 2) POI 搜索
        if not self.amap.enabled():
            print("[text] 高德 Key 缺失, 无法 geocode。回 --mock 或 --coords 模式。")
            sys.exit(3)
        self.report_progress("lookup")
        geo_results = self.selected_places or self._geocode_all(places)
        if len(geo_results) < 2:
            print(f"[text] geocode 成功数 {len(geo_results)} < 2, 失败")
            sys.exit(4)

        # 3 + 4) 调路径 (P0.4 自适应切片)
        #   - walking/bicycling 段: polyline 加到 walking_pts (街道级, 用于切片)
        #   - driving/transit 段: 不加到 walking_pts, 改存为 transit_marker (pin 显示)
        #   - all_waypoints_px 仍记全部, 仅用于无步行段时的切片 fallback,
        #     不再进 path (driving/transit 端点进 path 会在试玩里连成斜线)
        # 高德返回的是 GCJ-02: route 入参和距离估算直接用它,
        # 切片/投影一律用转成 WGS84 的 coords_wgs (OSM 是 WGS84)
        coords = [(g["lng"], g["lat"]) for g in geo_results]
        coords_wgs = [gcj02_to_wgs84(lng, lat) for lng, lat in coords]
        all_waypoints_px: List[Tuple[float, float]] = []
        walking_pts: List[Tuple[float, float]] = []   # 仅街道级 (用于 bbox 切片)
        seg_durations: List[float] = []               # 每段时长 (秒), 给 waypoint 计时用
        seg_modes: List[str] = []                     # 每段 mode, 给 walking/transit 时长分段用
        seg_routes: List[Optional[Dict[str, Any]]] = []  # 缓存 route 结果, 避免重复 API
        waypoint_metas: List[Dict[str, str]] = []

        has_subway = any(kw in self.text for kw in SUBWAY_KW)
        has_drive = any(kw in self.text for kw in DRIVE_KW)
        has_bike = any(kw in self.text for kw in BIKE_KW)
        first_walk_i: Optional[int] = None  # 第一段步行 / 骑行段的起点下标
        last_walk_j: Optional[int] = None   # 最后一段步行 / 骑行段的段下标

        self.report_progress("route")
        for i in range(len(coords) - 1):
            approx_km = approx_distance_km(coords[i], coords[i + 1])
            mode = self._pick_transport(approx_km, has_subway, has_drive, has_bike)
            if mode in ("walking", "bicycling"):
                if first_walk_i is None:
                    first_walk_i = i
                last_walk_j = i
            print(f"[text]   {geo_results[i]['name']} -> {geo_results[i + 1]['name']} "
                  f"({approx_km:.1f} km) 用 {mode}")
            route = self.amap.route(coords[i], coords[i + 1], mode=mode)
            seg_modes.append(mode)
            seg_routes.append(route)
            if route and route.get("polyline"):
                seg_duration = route.get("duration", 60.0)
                seg_durations.append(seg_duration)
                if mode in ("walking", "bicycling"):
                    # 街道级, 全部入 walking_pts (polyline 是 GCJ-02, 先转 WGS84)
                    pts = gcj02_to_wgs84_points(polyline_to_points(route["polyline"]))
                    walking_pts.extend(pts)
                    all_waypoints_px.extend(pts)
                elif mode == "transit":
                    # 只取 walking 子段 (高德返回里 walking_polyline 字段是 walking 部分)
                    wp_str = route.get("walking_polyline", "")
                    if wp_str:
                        wp_pts = gcj02_to_wgs84_points(polyline_to_points(wp_str))
                        walking_pts.extend(wp_pts)
                        all_waypoints_px.extend(wp_pts)
                    # 公交段端点也加到 all_waypoints (但不入 walking_pts)
                    all_waypoints_px.append(coords_wgs[i])
                    all_waypoints_px.append(coords_wgs[i + 1])
                    # 记 transit_marker (存 WGS84, 跟 grid/bbox 同系)
                    p.transit_markers.append(TransitMarker(
                        name=geo_results[i + 1]["name"],
                        transport="transit",
                        start_lng=coords_wgs[i][0], start_lat=coords_wgs[i][1],
                        end_lng=coords_wgs[i + 1][0], end_lat=coords_wgs[i + 1][1],
                        distance_m=route.get("distance", 0.0),
                        duration_sec=route.get("duration", 0.0),
                    ))
                else:  # driving
                    # 不入 walking_pts, 但记两端
                    all_waypoints_px.append(coords_wgs[i])
                    all_waypoints_px.append(coords_wgs[i + 1])
                    p.transit_markers.append(TransitMarker(
                        name=geo_results[i + 1]["name"],
                        transport="driving",
                        start_lng=coords_wgs[i][0], start_lat=coords_wgs[i][1],
                        end_lng=coords_wgs[i + 1][0], end_lat=coords_wgs[i + 1][1],
                        distance_m=route.get("distance", 0.0),
                        duration_sec=route.get("duration", 0.0),
                    ))
                waypoint_metas.append({"transport": mode, "label": geo_results[i + 1]["name"]})
            else:
                # P0.4: 即使 API 失败, 也不污染 walking_pts (避免 transit 端点撑大 bbox)
                print(f"[text]     {mode} 路径 API 失败, fallback 端点 only")
                all_waypoints_px.append(coords_wgs[i])
                all_waypoints_px.append(coords_wgs[i + 1])
                if mode in ("transit", "driving"):
                    # transit/driving 端点入 transit_marker
                    p.transit_markers.append(TransitMarker(
                        name=geo_results[i + 1]["name"],
                        transport=mode,
                        start_lng=coords_wgs[i][0], start_lat=coords_wgs[i][1],
                        end_lng=coords_wgs[i + 1][0], end_lat=coords_wgs[i + 1][1],
                        distance_m=0.0, duration_sec=0.0,
                    ))
                else:
                    # walking/bicycling fallback: 直线, 入 walking_pts
                    walking_pts.append(coords_wgs[i])
                    walking_pts.append(coords_wgs[i + 1])
                seg_durations.append(60.0)
                waypoint_metas.append({"transport": mode, "label": geo_results[i + 1]["name"]})

        # P0.4 自适应切片: 只在 walking 段切片 (避免 16km 公交把 bbox 撑爆)
        # fallback: walking_pts 为空时用 all_waypoints_px 末两点 (POI 周边切片)
        slice_path = walking_pts if walking_pts else all_waypoints_px[-2:] if len(all_waypoints_px) >= 2 else all_waypoints_px
        if not slice_path:
            print("[text] 无有效路径点, 无法切片")
            sys.exit(5)
        slice_info = slice_around_path(slice_path, radius_m=self.tile_radius_m)
        bbox = slice_info["bbox"]
        h_m, w_m = slice_info["size_m"]
        print(f"[text] 切片 (P0.4 自适应): {h_m:.0f}m x {w_m:.0f}m "
              f"(radius={self.tile_radius_m}m, walking_pts={len(walking_pts)}, "
              f"transit_markers={len(p.transit_markers)})")
        print(f"[text]   bbox: ({bbox[0]:.5f}, {bbox[1]:.5f}) -> ({bbox[2]:.5f}, {bbox[3]:.5f})")

        center_gcj = wgs84_to_gcj02(*slice_info["center"])
        poi_types = ("110000", "050000", "060000", "080000")
        place_names = [place["name"] for place in geo_results]
        with ThreadPoolExecutor(max_workers=3) as pool:
            map_request = pool.submit(self.osm.query_bbox, bbox) if self.osm.enabled() else None
            nearby_request = pool.submit(self._nearby_pois, center_gcj, poi_types)
            story_request = pool.submit(self.llm.generate_meta, self.text, place_names)
            self.report_progress("map")
            raw = map_request.result() if map_request else None
            self.report_progress("nearby")
            nearby_pois = nearby_request.result()
            if not story_request.done():
                self.report_progress("story")
            llm_meta = story_request.result()

        parsed_osm: Dict[str, List[Dict[str, Any]]] = {"roads": [], "buildings": [], "water": [], "green": []}
        if self.osm.enabled():
            if raw:
                parsed_osm = parse_overpass(raw)
                print(f"[text] OSM: {len(parsed_osm['roads'])} roads, "
                      f"{len(parsed_osm['buildings'])} buildings, "
                      f"{len(parsed_osm['water'])} water, "
                      f"{len(parsed_osm['green'])} green")
            else:
                print("[text] OSM query 失败, fallback 旧网格化 (只画 path)")
        else:
            print("[text] OSM 不可用, fallback 旧网格化")

        # 6.5) 调高德 place_around 拉 POI (中心点 + radius_m)
        if self.amap.enabled():
            for pois in nearby_pois:
                for poi in pois[:5]:  # 每类最多 5 个
                    cat_main = poi["type"].split(";")[0] if poi["type"] else "其他"
                    cat = POI_CATEGORY.get(cat_main, "other")
                    # 高德返回 GCJ-02, 存 WGS84 (跟 grid/bbox 同系, 投影直接用)
                    poi_lng, poi_lat = gcj02_to_wgs84(poi["location"][0], poi["location"][1])
                    p.pois.append(POI(
                        name=poi["name"],
                        type=poi["type"],
                        category=cat,
                        address=poi["address"],
                        lng=poi_lng,
                        lat=poi_lat,
                        distance=poi["distance"],
                    ))
            # 把 POI 投影到 grid
            for poi in p.pois:
                gx, gy = lnglat_to_grid_cell(poi.lng, poi.lat, bbox, (p.map.width, p.map.height))
                poi.grid_x = gx
                poi.grid_y = gy
            print(f"[text] POI: {len(p.pois)} 个 (周边 {self.tile_radius_m}m)")

        # 7) 网格化
        self.report_progress("build")
        # P0.4: path 投影只用 walking_pts (避免 transit 端点把 bbox 撑大)
        if not walking_pts and not all_waypoints_px:
            print("[text] 无有效路径点")
            sys.exit(5)
        # 把 transit_marker 的两端也投影到 grid (clamp 到边缘即可, 越界自然贴边)
        for tm in p.transit_markers:
            sx, sy = lnglat_to_grid_cell(tm.start_lng, tm.start_lat, bbox,
                                          (p.map.width, p.map.height))
            ex, ey = lnglat_to_grid_cell(tm.end_lng, tm.end_lat, bbox,
                                          (p.map.width, p.map.height))
            tm.start_grid_x = sx
            tm.start_grid_y = sy
            tm.end_grid_x = ex
            tm.end_grid_y = ey
            print(f"[text] transit_marker: {tm.name} ({tm.transport}) "
                  f"start=({sx},{sy}) end=({ex},{ey}) "
                  f"{tm.distance_m/1000:.1f}km / {tm.duration_sec:.0f}s")
        # path 投影: walking_pts 优先 (街道级, 不会被 transit 端点污染)
        # 路线贴路: 先造干净网格 (不带 overlay), 再沿路网 A* 寻路
        # (锚点吸附 + 逐段寻路, 局部吸附修不好的偏 25 格的路线也能回来),
        # 最后把路线叠到网格上。没 OSM 数据时回退到加密 + 局部吸附。
        path_source = walking_pts if walking_pts else all_waypoints_px
        grid_size = (p.map.width, p.map.height)
        follow_amap = all(
            mode == "walking" and route and route.get("polyline")
            for mode, route in zip(seg_modes, seg_routes)
        ) and len(walking_pts) >= 2
        if follow_amap:
            path_waypoints_grid = project_walking_track(path_source, bbox, grid_size, p.map.tile_size)

        if parsed_osm["roads"] or parsed_osm["buildings"]:
            # 用 OSM 真实数据 (P1.2: 多了 building_heights)
            grid, building_heights, osm_debug = osm_to_grid(
                parsed_osm, bbox, (p.map.width, p.map.height),
            )
            if not follow_amap:
                path_waypoints_grid = route_along_roads(
                    path_source, grid, bbox, grid_size,
                    osm_roads=parsed_osm.get("roads", []),
                    osm_water=parsed_osm.get("water", []))
                path_waypoints_grid = smooth_path_on_grid(path_waypoints_grid, grid)
                carve_route_passages(grid, path_waypoints_grid, building_heights)
                apply_path_overlay(grid, path_waypoints_grid)
            print(f"[text] Path 投影 ({'高德步行' if follow_amap else '沿路网寻路'}): "
                  f"{len(path_source)} -> {len(path_waypoints_grid)} grid points")
            p.map.grid = grid
            p.map.building_heights = building_heights
            n_with_levels = sum(1 for row in building_heights for v in row if v > 0)
            print(f"[text] P1.2 building_heights: {n_with_levels} cells have levels")
            # meta 加 OSM 调试信息
            p.meta.raw_text += f"\n[OSM] {osm_debug['road_count']}r/{osm_debug['building_count']}b (heights={n_with_levels} cells)"

            # P1.3: 室内 slots - 从 buildings 里挑有 interior 的, 算中心 cell
            for b in parsed_osm["buildings"]:
                if not b.get("interior"):
                    continue
                interior = b["interior"]
                nodes = b.get("nodes", [])
                if not nodes:
                    continue
                # 中心 (平均 lng, lat)
                avg_lng = sum(n[0] for n in nodes) / len(nodes)
                avg_lat = sum(n[1] for n in nodes) / len(nodes)
                gx, gy = lnglat_to_grid_cell(avg_lng, avg_lat, bbox,
                                              (p.map.width, p.map.height))
                name = b.get("name", "")
                p.interiors.append(InteriorSlot(
                    name=name,
                    category=interior["category"],
                    raw_tag=interior["raw_tag"],
                    lng=avg_lng, lat=avg_lat,
                    grid_x=gx, grid_y=gy,
                    has_name=bool(name),
                ))
            n_interiors = len(p.interiors)
            n_named = sum(1 for s in p.interiors if s.has_name)
            print(f"[text] P1.3 interior slots: {n_interiors} ({n_named} 有名字)")
            if n_interiors:
                cats = {}
                for s in p.interiors:
                    cats[s.category] = cats.get(s.category, 0) + 1
                print(f"[text]   分类: {cats}")
        else:
            # fallback: 没 OSM 数据, 加密 + 局部吸附 (无路网可寻)
            fallback_grid_path = densify_and_snap_route(
                path_source, [], bbox, (p.map.width, p.map.height))
            p.map.grid = build_grid_from_waypoints(fallback_grid_path, p.map.width, p.map.height)
            # Bug 1: 同 OSM 分支, 逐格点列视线法平滑 (穿楼/水保留拐点)
            if not follow_amap:
                path_waypoints_grid = smooth_path_on_grid(fallback_grid_path, p.map.grid)

        # 8) 组装 waypoint + meta
        # path 只含步行/骑行点, 总时长 = walking 段时长。
        # driving/transit 段不进 path (此前把两端当 teleport waypoint 追加进
        # p.path, Godot 会在两点间直线插值, 在试玩里画出一条横跨地图的斜线);
        # 开车/公交段的信息保留在 p.transit_markers 里, 不丢失。
        walking_total = sum(d for d, m in zip(seg_durations, seg_modes) if m in ("walking", "bicycling"))
        transit_total = sum(d for d, m in zip(seg_durations, seg_modes) if m in ("transit", "driving"))

        # walking 段: waypoint 沿 path, time 按累计路程分 (匀速走)。
        # 平滑后每段长度不一, 再按点序号分 t 会忽快忽慢, 所以改按路程分。
        # 注意: walking_pts 包含 pure walking + transit 的 walking sub-segments
        # 它们在视觉上都是在街道上走, 所以都标 walking
        n = len(path_waypoints_grid)
        cum_dist = [0.0]
        for a, b in zip(path_waypoints_grid, path_waypoints_grid[1:]):
            cum_dist.append(cum_dist[-1] + ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5)
        total_dist = cum_dist[-1] if cum_dist[-1] > 0 else 1.0
        for i, wp in enumerate(path_waypoints_grid):
            ratio = cum_dist[i] / total_dist
            t = ratio * walking_total
            # label 仍按 segment 分, 但 transport 统一 walking
            meta_idx = min(int(ratio * len(waypoint_metas)), len(waypoint_metas) - 1)
            meta = waypoint_metas[meta_idx]
            p.path.append(Waypoint(
                x=wp["x"], y=wp["y"], t=t,
                label=meta.get("label", f"pt_{i}"),
                transport="walking",   # path 里只有步行/骑行点, transit 段见 transit_markers
            ))

        # 按 t 排序
        p.path.sort(key=lambda w: w.t)
        if last_walk_j is not None and first_walk_i is not None:
            playable_stops = slice(first_walk_i, last_walk_j + 2)
            p.stops = build_stops(p, coords_wgs[playable_stops], bbox, parsed_osm,
                                  [place["name"] for place in geo_results[playable_stops]],
                                  confirmed_finish=follow_amap)
        else:
            p.stops = build_stops(p, coords_wgs, bbox, parsed_osm,
                                  [place["name"] for place in geo_results])
        cum_time = walking_total
        print(f"[text] Path waypoints: {len(p.path)} (walking={walking_total:.0f}s, "
              f"transit={transit_total:.0f}s 未计入 path/总时长, total={cum_time:.0f}s)")

        # 9) LLM 生成 meta + dialogs
        p.meta.weather = llm_meta.get("weather", "unknown")
        p.meta.mood = llm_meta.get("mood", "calm")
        p.meta.bgm = llm_meta.get("bgm", "")
        raw_dialogs = llm_meta.get("dialogs", [])
        # 对白时间按总时长 (cum_time, 仅步行段) 归一: LLM 回 t_offset 时
        # normalize 直接按比例换算, 天然落在总时长内, 无需重新生成。
        normalized = normalize_dialog_times(raw_dialogs, cum_time)
        # 兜底: LLM 若回的是绝对秒数 t (而非 t_offset), normalize 会原样保留,
        # 超出总时长时按比例整体压缩, 保证对白时间点始终落在总时长内。
        max_dt = max((d.get("t", 0) for d in normalized), default=0)
        if max_dt > cum_time > 0:
            scale = cum_time / max_dt
            for d in normalized:
                d["t"] = round(d.get("t", 0) * scale, 2)
            print(f"[text] 对白时间超出总时长, 按比例压缩 "
                  f"{max_dt:.1f}s -> {cum_time:.1f}s")
        for d in normalized:
            p.dialogs.append(Dialog(
                t=d.get("t", 0), speaker=d.get("speaker", "Me"), text=d.get("text", "")
            ))

        # 火红渲染上下文: write() 时自动画地图 (失败不丢 JSON)
        # 起 / 终点名取步行段的端点 (第一段常是开车 / 公交, 如"杭州市",
        # 步行实际从第二站开始, 不能拿 geo_results[0] 当起点名)。
        _start = geo_results[first_walk_i]["name"] if first_walk_i is not None \
            else (geo_results[0]["name"] if geo_results else "")
        _end = geo_results[last_walk_j + 1]["name"] if last_walk_j is not None \
            else (geo_results[-1]["name"] if geo_results else "")
        self._render_ctx = {
            "bbox": bbox,
            "osm": parsed_osm,
            "start_name": _start,
            "end_name": _end,
        }

        return p

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------
    def _nearby_pois(self, center: Tuple[float, float], categories: Tuple[str, ...]) -> list:
        if not self.amap.enabled():
            return []
        return [
            self.amap.place_around(center, radius=self.tile_radius_m, types=category)
            for category in categories
        ]

    def _extract_places(self) -> List[str]:
        """明确的两点路线优先，普通日记只采用原文中出现的地名。"""
        self.report_progress("extract")
        direct = re.fullmatch(
            r"[^\s从，。！？；、,!?;]{0,16}从([^，。！？；、,!?;\r\n]+?)"
            r"(?:步行|坐公交|坐地铁|开车|打车|骑车|走|出发)?(?:前往|到达|到|去)"
            r"([^，。！？；、,.!?;\r\n]+)[。！？.!?]?",
            self.text.strip(),
        )
        if direct and all(part.strip() for part in direct.groups()) and not re.search(
            r"然后|接着|途经|路过|再去|之后|以后", self.text
        ):
            return [part.strip() for part in direct.groups()]

        places = [
            name.strip() for name in self.llm.extract_places(self.text)
            if isinstance(name, str) and name.strip() and name.strip() in self.text
        ]
        if places and len(places) >= 2:
            return places
        return self._fuzzy_extract_via_amap()

    def _fuzzy_extract_via_amap(self) -> List[str]:
        """调高德 place_text 把日志里可能的地点片段查一遍, 匹配上的保留。
        精度规则 (通用, 不针对某条路线):
        - 候选按长度从长到短查, 真地名 (3-8 字) 先于 2 字碎片;
        - 仅接受与候选完全匹配的 POI 名称；
        - 城市名本身不算地点 (防 "济宁" 变成 "济宁市" 占一个点);
        - 查完所有候选再按在日志里的出现顺序排, 不中途停。
        """
        if not self.amap.enabled():
            return []
        candidates = self._extract_candidate_strings(self.text)[:self.fuzzy_candidate_limit]
        if not candidates:
            return []
        self.report_progress("lookup")
        print(f"[text] fuzzy: 尝试 {len(candidates)} 个候选")
        # real_name -> 首次在日志里的位置 (用于按路线顺序排)
        found: Dict[str, int] = {}
        for c in candidates:
            loc = self.amap.place_text(c, city=self.default_city)
            if not loc:
                continue
            lng, lat, real_name = loc
            # 城市名本身不算地点
            if real_name == self.default_city or real_name == self.default_city + "市":
                continue
            if real_name != c:
                continue
            if real_name in found:
                continue
            pos = self.text.find(real_name)
            if pos < 0:
                pos = self.text.find(c)
            found[real_name] = pos if pos >= 0 else 1 << 30
            print(f"[text]   ✓ {c} -> {real_name} ({lng:.4f}, {lat:.4f})")
        # 按在日志里的出现顺序排 (起点在前、终点在后)
        return sorted(found, key=lambda name: found[name])

    @staticmethod
    def _extract_candidate_strings(text: str) -> List[str]:
        """从 text 提取"可能地名"片段, 按长度从长到短排。
        算法:
        - 按非中文切分, 不截断 token (旧正则 {2,15} 会把 16 字日志
          截成 15 字, 丢掉末尾的 "街" 这类字);
        - 滑窗 3-8 字 (真地名多在这个范围), 长的先查;
        - 2 字片段排最后当兜底 (单独查 2 字极易错配, 必须后查
          且 _fuzzy_extract_via_amap 里只接受名字完全相等)。
        """
        tokens = re.findall(r'[\u4e00-\u9fff]{2,}', text)
        cands: List[str] = []
        for t in tokens:
            # 3-8 字窗口, 从长到短
            for n in range(min(8, len(t)), 2, -1):
                for i in range(0, len(t) - n + 1):
                    s = t[i:i + n]
                    if s not in cands:
                        cands.append(s)
            # 2 字兜底, 排最后
            for i in range(0, len(t) - 1):
                s = t[i:i + 2]
                if s not in cands:
                    cands.append(s)
        return cands[:80]  # 限制候选数 (防 API 限额)

    def _geocode_all(self, places: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for name in places[:6]:
            query = self._local_place_name(name)
            if not query:
                raise PlaceResolutionError(f"「{name}」只有城市名，请补充具体地点。")
            hits = self.amap.place_candidates(query, city=self.default_city)
            query_identity = query.replace("(", "").replace(")", "")
            branch = re.fullmatch(r"(.+?(?:广场|购物中心))\(?[^()]+店\)?", query)
            if branch and not any(
                self._local_place_name(hit[2]).replace("(", "").replace(")", "") == query_identity
                for hit in hits
            ):
                hits += self.amap.place_candidates(branch[1], city=self.default_city)
            exact = []
            branches = []
            for hit in dict.fromkeys(hits):
                resolved = self._local_place_name(hit[2])
                if resolved.replace("(", "").replace(")", "") == query_identity:
                    exact.append(hit)
                elif resolved.startswith(query + "(") and resolved.endswith(")"):
                    branches.append(hit)
            matches = exact or branches
            if len(matches) > 1:
                options = "、".join(dict.fromkeys(hit[2] for hit in matches[:3]))
                raise PlaceResolutionError(f"「{name}」有多个匹配地点（{options}），请填写具体分店或使用经纬度。")
            if matches:
                lng, lat, resolved = matches[0]
                results.append({"name": resolved, "lng": lng, "lat": lat})
                continue
            if re.search(r"\d+号$", query):
                point = self.amap.geocode(query, city=self.default_city, require_house_number=True)
                if point:
                    results.append({"name": name, "lng": point[0], "lat": point[1]})
                    continue
            raise PlaceResolutionError(f"在「{self.default_city}」找不到与「{name}」匹配的地点。请核对正式名称、地址或高德 Key。")
        return results

    def _local_place_name(self, name: str) -> str:
        normalized = re.sub(r"\s+", "", name).translate(str.maketrans("（）", "()")).casefold()
        city = self.default_city.strip().removesuffix("市").casefold()
        if city:
            normalized = normalized.removeprefix(city + "市") if normalized.startswith(city + "市") else normalized.removeprefix(city)
        return normalized

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
