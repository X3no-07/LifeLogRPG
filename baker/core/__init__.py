"""Baker core - 核心算法与数据契约"""
from .schema import LogPayload, Waypoint, Dialog, MapData, Meta, POI, Character
from .gridifier import (
    polyline_to_points,
    points_to_grid,
    build_grid_from_waypoints,
    bresenham_line,
    osm_to_grid,
)
from .time_scale import apply_time_scale
from .tiling import (
    slice_around_path,
    lnglat_to_grid_cell,
    meters_per_degree,
    PointLL,
    Bbox,
)

__all__ = [
    "LogPayload", "Waypoint", "Dialog", "MapData", "Meta", "POI", "Character",
    "polyline_to_points", "points_to_grid", "build_grid_from_waypoints", "bresenham_line",
    "osm_to_grid",
    "apply_time_scale",
    "slice_around_path", "lnglat_to_grid_cell", "meters_per_degree",
    "PointLL", "Bbox",
]
