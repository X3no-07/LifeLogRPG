"""高德地图 REST API 客户端

API 文档: https://lbs.amap.com/api/webservice/guide/api/

封装接口 (所有方法在 api_key 为空时返回 None, 不会抛异常):
- geocode(address, city) -> (lng, lat) | None
- place_text(keywords, city, types) -> (lng, lat, name) | None
- route(origin, dest, mode) -> {distance, duration, polyline, steps} | None
  mode: walking / bicycling / driving / transit
"""
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
    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Point]:
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
                loc = data["geocodes"][0]["location"]
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
        if not self.enabled():
            return None
        params: Dict[str, Any] = {
            "key": self.api_key,
            "keywords": keywords,
            "city": city,
            "citylimit": "true",
            "output": "JSON",
            "offset": 1,
        }
        if types:
            params["types"] = types
        try:
            r = self._requests.get(f"{self.base_url}/place/text", params=params, timeout=self.timeout)
            data = r.json()
            if data.get("status") == "1" and data.get("pois"):
                p = data["pois"][0]
                lng, lat = p["location"].split(",")
                return (float(lng), float(lat), p.get("name", keywords))
        except Exception as e:
            self._log(f"place_text error: {e}")
        return None

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
        return {
            "distance": float(path.get("distance", 0)),
            "duration": float(path.get("duration", 0)),
            "polyline": full_polyline,
            "steps": steps_data,
        }

    def _parse_transit(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        transits = data.get("route", {}).get("transits", [])
        if not transits:
            return None
        t = transits[0]
        all_pts: List[Point] = []
        total_dist = 0.0
        total_dur = 0.0
        for seg in t.get("segments", []):
            if "bus" in seg and seg["bus"].get("buslines"):
                bl = seg["bus"]["buslines"][0]
                pts = self._transit_polyline_to_points(bl.get("polyline", ""))
                all_pts.extend(pts)
                total_dist += float(bl.get("distance", 0))
                total_dur += float(bl.get("duration", 0))
            if "walking" in seg:
                pts = self._transit_polyline_to_points(seg["walking"].get("polyline", ""))
                all_pts.extend(pts)
                total_dist += float(seg["walking"].get("distance", 0))
                total_dur += float(seg["walking"].get("duration", 0))
        polyline = ";".join(f"{p[0]},{p[1]}" for p in all_pts)
        return {
            "distance": total_dist,
            "duration": total_dur,
            "polyline": polyline,
            "steps": [{"instruction": f"公交段 {i}", "polyline": polyline} for i in range(len(all_pts))],
        }

    @staticmethod
    def _transit_polyline_to_points(polyline: str) -> List[Point]:
        # 公交的 polyline 也是 "lng,lat;lng,lat" 格式
        from ..core.gridifier import polyline_to_points
        return polyline_to_points(polyline)
