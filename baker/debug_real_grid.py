#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug: 用硬编码北京坐标, 端到端跑 OSM 网格化"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baker.clients.osm import OsmClient, parse_overpass
from baker.core.gridifier import osm_to_grid
from baker.core.tiling import slice_around_path

# 天安门 → 王府井 (lng, lat)
path = [
    (116.397, 39.909),  # 天安门
    (116.410, 39.915),  # 王府井
]

# 切片
print("[1] 切片 (800m 半径) ...")
slice_info = slice_around_path(path, radius_m=800)
bbox = slice_info["bbox"]
h_m, w_m = slice_info["size_m"]
print(f"  bbox: ({bbox[0]:.5f}, {bbox[1]:.5f}) -> ({bbox[2]:.5f}, {bbox[3]:.5f})")
print(f"  size: {h_m:.0f}m x {w_m:.0f}m")

# 拉 OSM
print("\n[2] OSM query ...")
osm = OsmClient(verbose=False)
raw = osm.query_bbox(bbox)
if not raw:
    print("  FAIL")
    sys.exit(1)
print(f"  Got {len(raw.get('elements', []))} elements")
parsed = parse_overpass(raw)
print(f"  Roads: {len(parsed['roads'])}")
print(f"  Buildings: {len(parsed['buildings'])}")
print(f"  Water: {len(parsed['water'])}")
print(f"  Green: {len(parsed['green'])}")

# 打印前 5 个有名字的路
print("\n  前 5 个路 (有名字):")
for r in parsed["roads"][:5]:
    if r["name"]:
        print(f"    {r['highway_type']:12} {r['name']:30} ({len(r['nodes'])} nodes)")

# 网格化
print("\n[3] 网格化 (80x60) ...")
grid, heights, debug = osm_to_grid(parsed, bbox, (80, 60))
print(f"  cell counts: {debug['cell_counts']}")

# 打印前 5 行可视化
print("\n[4] 地图可视化 (前 5 行 + 50-55 行)")
chars = {0: ".", 1: "#", 2: "B", 3: "~", 4: "T", 5: "-", 6: "P", 7: "_"}
for y in list(range(0, 5)) + list(range(50, 55)):
    line = f"  {y:2d} | "
    for x in range(80):
        c = grid[y][x] if y < len(grid) and x < len(grid[y]) else 0
        line += chars.get(c, "?")
    print(line)

# 写一个简单的 JSON 摘要
out = {
    "bbox": bbox,
    "size_m": [h_m, w_m],
    "osm_counts": {k: len(v) for k, v in parsed.items()},
    "cell_counts": debug["cell_counts"],
    "sample_roads": [
        {"type": r["highway_type"], "name": r["name"], "node_count": len(r["nodes"])}
        for r in parsed["roads"][:5] if r["name"]
    ],
    "sample_buildings": [
        {"name": b["name"], "node_count": len(b["nodes"])}
        for b in parsed["buildings"][:5] if b["name"]
    ],
}
print(f"\n[5] JSON 摘要:")
print(json.dumps(out, ensure_ascii=False, indent=2))
