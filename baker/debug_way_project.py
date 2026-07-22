#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug: 单个 way 投影到 grid 看坐标"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baker.clients.osm import OsmClient, parse_overpass
from baker.core.tiling import slice_around_path

path = [(116.397, 39.909), (116.410, 39.915)]
slice_info = slice_around_path(path, radius_m=800)
bbox = slice_info["bbox"]
gw, gh = 80, 60

print(f"bbox: {bbox}")
print(f"grid: {gw}x{gh}")

osm = OsmClient()
raw = osm.query_bbox(bbox)
parsed = parse_overpass(raw)

# 取第一个 building 看投影
if parsed["buildings"]:
    b = parsed["buildings"][0]
    print(f"\n[building] name={b['name']}, nodes={len(b['nodes'])}")
    for i, n in enumerate(b["nodes"][:6]):
        lng, lat = n
        # _lnglat_to_grid_xy 算
        min_lat, min_lng, max_lat, max_lng = bbox
        nx = (lng - min_lng) / (max_lng - min_lng)
        ny = 1.0 - (lat - min_lat) / (max_lat - min_lat)
        gx = int(nx * gw)
        gy = int(ny * gh)
        print(f"  node {i}: (lng={lng:.5f}, lat={lat:.5f}) -> grid ({gx}, {gy})")

# 第一个 road
if parsed["roads"]:
    r = parsed["roads"][0]
    print(f"\n[road] {r['highway_type']} {r['name']}, nodes={len(r['nodes'])}")
    for i, n in enumerate(r["nodes"][:6]):
        lng, lat = n
        min_lat, min_lng, max_lat, max_lng = bbox
        nx = (lng - min_lng) / (max_lng - min_lng)
        ny = 1.0 - (lat - min_lat) / (max_lat - min_lat)
        gx = int(nx * gw)
        gy = int(ny * gh)
        print(f"  node {i}: (lng={lng:.5f}, lat={lat:.5f}) -> grid ({gx}, {gy})")

# 试 _draw_polygon: 单 building
from baker.core.gridifier import _draw_polygon
if parsed["buildings"]:
    b = parsed["buildings"][0]
    grid = [[0 for _ in range(gw)] for _ in range(gh)]
    _draw_polygon(grid, b["nodes"], bbox, (gw, gh), value=2, fill=True)
    counts = {0:0, 1:0, 2:0}
    for row in grid:
        for c in row:
            counts[c] = counts.get(c, 0) + 1
    print(f"\n[single building draw] cell counts: {counts}")
    # 打印 grid
    chars = {0:".", 1:"#", 2:"B"}
    for y in range(gh):
        line = f"  {y:2d} | "
        for x in range(gw):
            line += chars.get(grid[y][x], "?")
        print(line)
