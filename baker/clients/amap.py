"""高德地图 REST API 客户端

API 文档: https://lbs.amap.com/api/webservice/guide/api/

封装接口 (所有方法在 api_key 为空时返回 None, 不会抛异常):
- geocode(address, city) -> (lng, lat) | None
- place_text(keywords, city, types) -> (lng, lat, name) | None
- route(origin, dest, mode) -> {distance, duration, polyline, steps} | None
  mode: walking / bicycling / driving / transit
"""
import math
import sys
from typing import Any, Dict, List, Optional, Tuple

Point = Tuple[float, float]


class AmapClient:
    def __init__(self, api_key: str, base_url: str = "https://restapi.amap.com/v3",
                 timeout: int = 10, verbose: bool = False):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose
        self._requests = None
        if api_key:
            try:
                import requests  # type: ignore
                self._requests = requests
            except ImportError:
                print("[amap] WARN: requests 未安装, pip install requests")

    # ------------------------------------------------------------------
    #  状态
    # ------------------------------------------------------------------
    def enabled(self) -> bool:
        """API Key + requests 都就绪才返回 True"""
        return bool(self.api_key) and self._requests is not None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[amap] {msg}", file=sys.stderr)

    # ------------------------------------------------------------------
    #  Geocode / Place Text
    # ------------------------------------------------------------------
    def geocode(self, address: str, city: Optional[str] = None, *,
                require_house_number: bool = False) -> Optional[Point]:
        """地址 -> (lng, lat), 适合 "北京市东城区王府井大街" 这种完整地址"""
        if not self.enabled():
            return None
        params: Dict[str, Any] = {"key": self.api_key, "address": address, "output": "JSON"}
        if city:
            params["city"] = city
        try:
            r = self._requests.get(f"{self.base_url}/geocode/geo", params=params, timeout=self.timeout)
            data = r.json()
            if data.get("status") == "1" and data.get("geocodes"):
                match = data["geocodes"][0]
                if require_house_number and (
                    match.get("level") != "门牌号"
                    or not str(match.get("formatted_address", "")).endswith(address)
                ):
                    return None
                loc = match["location"]
                lng, lat = loc.split(",")
                return (float(lng), float(lat))
        except Exception as e:
            self._log(f"geocode error: {e}")
        return None

    def place_text(self, keywords: str, city: str = "北京",
                   types: Optional[str] = None) -> Optional[Tuple[float, float, str]]:
        """POI 关键字搜索 -> (lng, lat, name)
        比 geocode 更适合 POI 简称 (王府井/国贸等), 支持 city 限定避免全国同名
        """
        hits = self.place_candidates(keywords, city, types, limit=1)
        return hits[0] if hits else None

    def place_candidates(self, keywords: str, city: str = "北京",
                         types: Optional[str] = None, *,
                         limit: int = 15) -> List[Tuple[float, float, str]]:
        if not self.enabled():
            return []
        params: Dict[str, Any] = {
            "key": self.api_key,
            "keywords": keywords,
            "city": city,
            "citylimit": "true",
            "output": "JSON",
            "offset": limit,
        }
        if types:
            params["types"] = types
        try:
            r = self._requests.get(f"{self.base_url}/place/text", params=params, timeout=self.timeout)
            data = r.json()
            hits = []
            if data.get("status") == "1" and data.get("pois"):
                for poi in data["pois"]:
                    try:
                        lng, lat = map(float, poi.get("location", "").split(","))
                    except (AttributeError, ValueError):
                        continue
                    if poi.get("name"):
                        hits.append((lng, lat, poi["name"]))
            return hits
        except Exception as e:
            self._log(f"place_text error: {e}")
        return []

    def suggest_places(self, query: str, city: str) -> List[Dict[str, Any]]:
        if not self.enabled():
            raise OSError("地图服务未配置")
        params = {"key": self.api_key, "keywords": query, "city": city,
                  "citylimit": "true", "output": "JSON"}
        choices = []
        seen = set()
        succeeded = False
        for path, field, extra in (
            ("assistant/inputtips", "tips", {"datatype": "all"}),
            ("place/text", "pois", {"offset": 10}),
        ):
            try:
                response = self._requests.get(f"{self.base_url}/{path}",
                                              params={**params, **extra}, timeout=self.timeout)
                data = response.json()
            except (self._requests.exceptions.RequestException, ValueError):
                continue
            if data.get("status") != "1":
                continue
            succeeded = True
            for item in data.get(field, []):
                name = item.get("name")
                location = item.get("location")
                if not isinstance(name, str) or not name or not isinstance(location, str):
                    continue
                try:
                    lng, lat = map(float, location.split(","))
                except ValueError:
                    continue
                if not (math.isfinite(lng) and math.isfinite(lat)
                        and -180 <= lng <= 180 and -90 <= lat <= 90):
                    continue
                identity = (name, lng, lat)
                if identity in seen:
                    continue
                seen.add(identity)
                address = " ".join(value for value in
                                   (item.get("district") or item.get("adname"), item.get("address"))
                                   if isinstance(value, str) and value)
                choices.append({"name": name, "address": address, "lng": lng, "lat": lat})
                if len(choices) == 5:
                    return choices
            if choices:
                return choices
        if not succeeded:
            raise OSError("地图服务查询失败")
        return choices

    def place_around(self, location: Tuple[float, float], radius: int = 500,
                     types: Optional[str] = None,
                     keywords: Optional[str] = None) -> List[Dict[str, Any]]:
        """POI 周边搜索: 中心点 + 半径米
        location: (lng, lat) 高德坐标系
        radius: 米, 默认 500
        types: 高德 POI 类型码 (逗号分隔), e.g. "050000"=餐饮, "060000"=购物
        keywords: 关键词, 可选

        返回: [{"name", "location": (lng, lat), "type", "address", "distance"}, ...]
        """
        if not self.enabled():
            return []
        params: Dict[str, Any] = {
            "key": self.api_key,
            "location": f"{location[0]},{location[1]}",
            "radius": radius,
            "offset": 20,  # 每次最多 20 个
            "output": "JSON",
        }
        if types:
            params["types"] = types
        if keywords:
            params["keywords"] = keywords
        try:
            r = self._requests.get(f"{self.base_url}/place/around", params=params, timeout=self.timeout)
            data = r.json()
            if data.get("status") == "1" and data.get("pois"):
                out: List[Dict[str, Any]] = []
                for p in data["pois"]:
                    lng, lat = p["location"].split(",")
                    out.append({
                        "name": p.get("name", ""),
                        "type": p.get("type", ""),
                        "address": p.get("address", ""),
                        "location": (float(lng), float(lat)),
                        "distance": int(p.get("distance", 0)),
                    })
                return out
            else:
                self._log(f"place_around fail: status={data.get('status')} info={data.get('info')} count={data.get('count')}")
        except Exception as e:
            self._log(f"place_around error: {e}")
        return []

    # ------------------------------------------------------------------
    #  Route
    # ------------------------------------------------------------------
    _ENDPOINTS = {
        "walking": "direction/walking",
        "bicycling": "direction/bicycling",
        "driving": "direction/driving",
        "transit": "direction/transit/integrated",
    }

    def route(self, origin: Point, dest: Point, mode: str = "walking") -> Optional[Dict[str, Any]]:
        """路径规划 -> {distance (m), duration (s), polyline, steps: [{instruction, road, ...}]}
        mode: walking / bicycling / driving / transit
        """
        if not self.enabled():
            return None
        endpoint = self._ENDPOINTS.get(mode, "direction/walking")
        params: Dict[str, Any] = {
            "key": self.api_key,
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{dest[0]},{dest[1]}",
            "output": "JSON",
        }
        if mode == "transit":
            params["city"] = "北京"  # 公交 API 必须 city
        try:
            r = self._requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=self.timeout)
            data = r.json()
            if data.get("status") != "1":
                self._log(f"route fail: {data.get('info')} / {data.get('infocode')}")
                return None
            if mode == "transit":
                return self._parse_transit(data)
            return self._parse_walk_drive(data)
        except Exception as e:
            self._log(f"route error: {e}")
        return None

    def _parse_walk_drive(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        paths = data.get("route", {}).get("paths", [])
        if not paths:
            return None
        path = paths[0]
        steps_data: List[Dict[str, Any]] = []
        for s in path.get("steps", []):
            steps_data.append({
                "instruction": s.get("instruction", ""),
                "road": s.get("road", ""),
                "action": s.get("action", ""),
                "distance": float(s.get("distance", 0)),
                "duration": float(s.get("duration", 0)),
                "polyline": s.get("polyline", ""),
            })
        full_polyline = ";".join(s["polyline"] for s in steps_data)
        # walking/bicycling 是街道级, 全部当作 walking_polyline
        # driving 段不算 walking (开车不可能在 grid 上画)
        return {
            "distance": float(path.get("distance", 0)),
            "duration": float(path.get("duration", 0)),
            "polyline": full_polyline,
            "steps": steps_data,
        }

    def _parse_transit(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析公交/地铁换乘方案
        返回字段:
          - distance / duration: 总和
          - polyline: 全部段拼接 (兼容旧逻辑, 不区分 walking/bus)
          - walking_polyline: 只拼接 walking 段 (用于自适应切片)
          - segments: [{mode: "walking"|"bus", polyline, distance, duration}, ...]
        """
        transits = data.get("route", {}).get("transits", [])
        if not transits:
            return None
        t = transits[0]
        all_pts: List[Point] = []
        walking_pts: List[Point] = []
        total_dist = 0.0
        total_dur = 0.0
        seg_list: List[Dict[str, Any]] = []
        for seg in t.get("segments", []):
            if "bus" in seg and seg["bus"].get("buslines"):
                bl = seg["bus"]["buslines"][0]
                poly_str = bl.get("polyline", "")
                pts = self._transit_polyline_to_points(poly_str)
                all_pts.extend(pts)
                dist = float(bl.get("distance", 0))
                dur = float(bl.get("duration", 0))
                total_dist += dist
                total_dur += dur
                seg_list.append({
                    "mode": "bus",
                    "polyline": poly_str,
                    "distance": dist,
                    "duration": dur,
                })
            if "walking" in seg:
                poly_str = seg["walking"].get("polyline", "")
                pts = self._transit_polyline_to_points(poly_str)
                all_pts.extend(pts)
                walking_pts.extend(pts)
                dist = float(seg["walking"].get("distance", 0))
                dur = float(seg["walking"].get("duration", 0))
                total_dist += dist
                total_dur += dur
                seg_list.append({
                    "mode": "walking",
                    "polyline": poly_str,
                    "distance": dist,
                    "duration": dur,
                })
        polyline = ";".join(f"{p[0]},{p[1]}" for p in all_pts)
        walking_polyline = ";".join(f"{p[0]},{p[1]}" for p in walking_pts)
        return {
            "distance": total_dist,
            "duration": total_dur,
            "polyline": polyline,
            "walking_polyline": walking_polyline,
            "segments": seg_list,
        }

    @staticmethod
    def _transit_polyline_to_points(polyline: str) -> List[Point]:
        # 公交的 polyline 也是 "lng,lat;lng,lat" 格式
        from ..core.gridifier import polyline_to_points
        return polyline_to_points(polyline)
