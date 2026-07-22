"""坐标模式: 用户提供经纬度序列

格式: "lng,lat;lng,lat;lng,lat;..."
也用 OSM 真实数据 (只要 Key 配置好) + 高德 POI 周边
P0.x 升级: 调高德 route 拿 polyline 走真实路, 不走直线
P0.4 升级: 自适应切片 — long transit 不爆 bbox
"""
import sys
from typing import List, Tuple, Optional, Dict, Any

from ..core.gridifier import (
    points_to_grid, build_grid_from_waypoints, compute_bounds, osm_to_grid,
    polyline_to_points, approx_distance_km,
)
from ..core.tiling import slice_around_path, lnglat_to_grid_cell
from ..core.schema import Waypoint, Dialog, POI, TransitMarker, InteriorSlot
from ..clients.osm import OsmClient, parse_overpass
from ..clients.amap import AmapClient
from .base import BaseMode

# 跟 text.py 同步
POI_CATEGORY = {
    "餐饮服务": "food", "购物服务": "shop", "生活服务": "life",
    "体育休闲服务": "leisure", "医疗保健服务": "medical", "住宿服务": "hotel",
    "风景名胜": "scenic", "交通设施服务": "transport", "政府机构及社会团体": "gov",
    "科教文化服务": "edu", "金融保险服务": "finance", "公司企业": "company",
    "公共设施": "public", "其他": "other",
}


class CoordsMode(BaseMode):
    def __init__(self, name: str, coords_str: str, config=None):
        super().__init__(name, config)
        try:
            self.coords: List[Tuple[float, float]] = [
                tuple(float(x) for x in p.split(",")) for p in coords_str.split(";")
            ]
        except ValueError as e:
            print(f"[coords] 解析失败: {e}")
            sys.exit(1)
        self.osm = OsmClient(timeout=int(self.config.get("bake", {}).get("osm_timeout_sec", 30)))
        self.amap = AmapClient(api_key=self.config.get("amap", {}).get("api_key", ""))
        self.tile_radius_m = int(self.config.get("bake", {}).get("tile_radius_m", 800))

    def run(self) -> "LogPayload":
        p = self.payload
        p.meta.title = "坐标生成日志"
        p.meta.raw_text = ";".join(f"{c[0]},{c[1]}" for c in self.coords)

        if len(self.coords) < 2:
            print("[coords] 至少 2 个坐标点")
            sys.exit(2)

        # P0.4: 调高德 route 拿真实路 polyline, 拆分 walking_pts vs transit_markers
        all_route_points: List[Tuple[float, float]] = []
        walking_pts: List[Tuple[float, float]] = []
        seg_durations: List[float] = []
        seg_modes: List[str] = []

        for i in range(len(self.coords) - 1):
            a = self.coords[i]
            b = self.coords[i + 1]
            approx_km = approx_distance_km(a, b)
            if approx_km < 0.05:
                # 太近, 直接连
                all_route_points.append(a)
                all_route_points.append(b)
                walking_pts.append(a)
                walking_pts.append(b)
                seg_durations.append(30.0)
                seg_modes.append("walking")
                continue
            # 自动选 transport: < 5km walking, >= 5km driving
            mode = "walking" if approx_km < 5.0 else "driving"
            route = self.amap.route(a, b, mode=mode)
            seg_modes.append(mode)
            if route and route.get("polyline"):
                pts = polyline_to_points(route["polyline"])
                all_route_points.extend(pts)
                seg_durations.append(route.get("duration", 60.0))
                if mode in ("walking", "bicycling"):
                    walking_pts.extend(pts)
                else:
                    # driving: 不入 walking_pts, 记 transit_marker
                    all_route_points.append(a)
                    all_route_points.append(b)
                    p.transit_markers.append(TransitMarker(
                        name=f"pt_{i + 1}",
                        transport="driving",
                        start_lng=a[0], start_lat=a[1],
                        end_lng=b[0], end_lat=b[1],
                        distance_m=route.get("distance", 0.0),
                        duration_sec=route.get("duration", 0.0),
                    ))
                print(f"[coords]   {a} -> {b} ({approx_km:.1f}km, {mode}): "
                      f"{len(pts)} polyline pts, {route.get('duration', 0):.0f}s")
            else:
                all_route_points.append(a)
                all_route_points.append(b)
                walking_pts.append(a)
                walking_pts.append(b)
                seg_durations.append(60.0)
                print(f"[coords]   {a} -> {b} ({approx_km:.1f}km): route 失败, 用直线")
        all_route_points.append(self.coords[-1])

        # P0.4 自适应切片: 只在 walking_pts 段切片
        # fallback: walking_pts 为空时 (纯 driving/transit), slice 第一个 coord
        if walking_pts:
            slice_path = walking_pts
        elif self.coords:
            # 用第一个点为中心, 半径 radius_m 切
            first_lng, first_lat = self.coords[0]
            slice_path = [(first_lng, first_lat)]
        else:
            slice_path = all_route_points
        slice_info = slice_around_path(slice_path, radius_m=self.tile_radius_m)
        bbox = slice_info["bbox"]
        h_m, w_m = slice_info["size_m"]
        print(f"[coords] 切片 (P0.4 自适应): {h_m:.0f}m x {w_m:.0f}m "
              f"(radius={self.tile_radius_m}m, walking_pts={len(walking_pts)}, "
              f"transit_markers={len(p.transit_markers)})")

        parsed_osm = {"roads": [], "buildings": [], "water": [], "green": []}
        if self.osm.enabled():
            raw = self.osm.query_bbox(bbox)
            if raw:
                parsed_osm = parse_overpass(raw)
                print(f"[coords] OSM: {len(parsed_osm['roads'])}r "
                      f"{len(parsed_osm['buildings'])}b "
                      f"{len(parsed_osm['water'])}w "
                      f"{len(parsed_osm['green'])}g")

        # P0.3: 调高德 place_around 拉 POI
        if self.amap.enabled():
            center_lng, center_lat = slice_info["center"]
            for types_filter, label in [("110000", "scenic"), ("050000", "food"),
                                          ("060000", "shop"), ("080000", "life")]:
                pois = self.amap.place_around((center_lng, center_lat),
                                              radius=self.tile_radius_m,
                                              types=types_filter)
                for poi in pois[:5]:
                    cat_main = poi["type"].split(";")[0] if poi["type"] else "其他"
                    cat = POI_CATEGORY.get(cat_main, "other")
                    p.pois.append(POI(
                        name=poi["name"], type=poi["type"], category=cat,
                        address=poi["address"],
                        lng=poi["location"][0], lat=poi["location"][1],
                        distance=poi["distance"],
                    ))
            for poi in p.pois:
                gx, gy = lnglat_to_grid_cell(poi.lng, poi.lat, bbox, (p.map.width, p.map.height))
                poi.grid_x = gx
                poi.grid_y = gy
            print(f"[coords] POI: {len(p.pois)} 个 (周边 {self.tile_radius_m}m)")

        # transit_marker 投影到 grid (越界 clamp 到边缘)
        for tm in p.transit_markers:
            sx, sy = lnglat_to_grid_cell(tm.start_lng, tm.start_lat, bbox,
                                          (p.map.width, p.map.height))
            ex, ey = lnglat_to_grid_cell(tm.end_lng, tm.end_lat, bbox,
                                          (p.map.width, p.map.height))
            tm.start_grid_x = sx
            tm.start_grid_y = sy
            tm.end_grid_x = ex
            tm.end_grid_y = ey
            print(f"[coords] transit_marker: {tm.name} ({tm.transport}) "
                  f"start=({sx},{sy}) end=({ex},{ey}) "
                  f"{tm.distance_m/1000:.1f}km / {tm.duration_sec:.0f}s")

        # 路径投影: 用 walking_pts (避免 transit 端点污染)
        if walking_pts:
            path_source = walking_pts
            path_bounds = compute_bounds(path_source)
            path_waypoints_grid = points_to_grid(path_source, path_bounds, (p.map.width, p.map.height))
            print(f"[coords] Path 投影: {len(path_source)} -> {len(path_waypoints_grid)} grid points")
        else:
            # 全 driving/transit: 无 street-level path, 用单点 placeholder
            path_waypoints_grid = []
            print(f"[coords] Path 投影: 无 walking 段, path 仅含 transit teleport")

        if parsed_osm["roads"] or parsed_osm["buildings"]:
            # P1.2: 多回传 building_heights
            grid, building_heights, osm_debug = osm_to_grid(
                parsed_osm, bbox, (p.map.width, p.map.height),
                path_overlay_waypoints=path_waypoints_grid,
            )
            p.map.grid = grid
            p.map.building_heights = building_heights
            n_with_levels = sum(1 for row in building_heights for v in row if v > 0)
            print(f"[coords] P1.2 building_heights: {n_with_levels} cells have levels")
            p.meta.raw_text += f"\n[OSM] {osm_debug['road_count']}r/{osm_debug['building_count']}b (heights={n_with_levels} cells)"

            # P1.3: 室内 slots
            for b in parsed_osm["buildings"]:
                if not b.get("interior"):
                    continue
                interior = b["interior"]
                nodes = b.get("nodes", [])
                if not nodes:
                    continue
                avg_lng = sum(n[0] for n in nodes) / len(nodes)
                avg_lat = sum(n[1] for n in nodes) / len(nodes)
                gx, gy = lnglat_to_grid_cell(avg_lng, avg_lat, bbox,
                                              (p.map.width, p.map.height))
                name = b.get("name", "")
                p.interiors.append(InteriorSlot(
                    name=name, category=interior["category"],
                    raw_tag=interior["raw_tag"],
                    lng=avg_lng, lat=avg_lat,
                    grid_x=gx, grid_y=gy, has_name=bool(name),
                ))
            print(f"[coords] P1.3 interior slots: {len(p.interiors)}")
        else:
            p.map.grid = build_grid_from_waypoints(path_waypoints_grid, p.map.width, p.map.height)

        # 时间分布: walking_total + transit_total
        walking_total = sum(d for d, m in zip(seg_durations, seg_modes) if m in ("walking", "bicycling"))
        transit_total = sum(d for d, m in zip(seg_durations, seg_modes) if m == "driving")

        # walking 段 waypoint (沿 path, time = ratio * walking_total)
        n = len(path_waypoints_grid)
        for i, wp in enumerate(path_waypoints_grid):
            t = (i / max(n - 1, 1)) * walking_total
            p.path.append(Waypoint(
                x=wp["x"], y=wp["y"], t=t,
                label=f"pt_{i}", transport="walking",
            ))

        # transit/driving 段: 加 2 个 teleport waypoint (start + end)
        # start: t=walking_total+transit_offset, position=start_grid
        # end:   t=walking_total+transit_offset+seg_dur, position=end_grid
        # Godot 端插值, transport.gd 触发 fade
        tm_iter = iter(p.transit_markers)
        transit_offset = 0.0
        for i, mode in enumerate(seg_modes):
            if mode == "driving":
                tm = next(tm_iter, None)
                if tm:
                    p.path.append(Waypoint(
                        x=tm.start_grid_x, y=tm.start_grid_y,
                        t=walking_total + transit_offset,
                        label=tm.name + "_depart",
                        transport="driving",
                    ))
                    p.path.append(Waypoint(
                        x=tm.end_grid_x, y=tm.end_grid_y,
                        t=walking_total + transit_offset + seg_durations[i],
                        label=tm.name + "_arrive",
                        transport="driving",
                    ))
                transit_offset += seg_durations[i]
        p.path.sort(key=lambda w: w.t)
        print(f"[coords] Path waypoints: {len(p.path)} (walking={walking_total:.0f}s, "
              f"transit={transit_total:.0f}s)")

        return p
