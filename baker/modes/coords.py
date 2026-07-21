"""坐标模式: 用户提供经纬度序列

格式: "lng,lat;lng,lat;lng,lat;..."
"""
import sys
from typing import List, Tuple

from ..core.gridifier import (
    points_to_grid, build_grid_from_waypoints, compute_bounds,
)
from ..core.schema import Waypoint, Dialog
from .base import BaseMode


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

    def run(self) -> "LogPayload":
        p = self.payload
        p.meta.title = "坐标生成日志"
        p.meta.raw_text = ";".join(f"{c[0]},{c[1]}" for c in self.coords)

        if len(self.coords) < 2:
            print("[coords] 至少 2 个坐标点")
            sys.exit(2)

        bounds = compute_bounds(self.coords)
        waypoints_grid = points_to_grid(self.coords, bounds, (p.map.width, p.map.height))
        p.map.grid = build_grid_from_waypoints(waypoints_grid, p.map.width, p.map.height)

        for i, wp in enumerate(waypoints_grid):
            p.path.append(Waypoint(
                x=wp["x"], y=wp["y"], t=float(i) * 1.5,
                label=f"pt_{i}", transport="walking",
            ))

        return p
