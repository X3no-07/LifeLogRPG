#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug: 实际调 OSM Overpass + 高德 POI 周边, 看真实数据"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baker.clients.osm import OsmClient, parse_overpass, compute_bbox_from_points, expand_bbox
from baker.clients.amap import AmapClient
from baker.config import load_config

config = load_config()
amap = AmapClient(api_key=config.get("amap", {}).get("api_key", ""))
osm = OsmClient(verbose=True)
amap = AmapClient(api_key=config.get("amap", {}).get("api_key", ""), verbose=True)

# 测试 1: 调 OSM (北京天安门附近)
print("=" * 60)
print("[1] OSM query: 天安门 0.005° bbox")
print("=" * 60)
bbox = (39.897, 116.390, 39.907, 116.410)  # 约 1km x 1km
raw = osm.query_bbox(bbox)
if raw:
    print(f"  Got {len(raw.get('elements', []))} elements")
    parsed = parse_overpass(raw)
    print(f"  Roads: {len(parsed['roads'])}")
    for r in parsed["roads"][:3]:
        print(f"    {r['highway_type']:12} {r['name'][:20]:20} ({len(r['nodes'])} nodes)")
    print(f"  Buildings: {len(parsed['buildings'])}")
    for b in parsed["buildings"][:3]:
        print(f"    {b['building']:12} {b['name'][:20]:20} ({len(b['nodes'])} nodes)")
    print(f"  Water: {len(parsed['water'])}")
    for w in parsed["water"][:3]:
        print(f"    {w['type']:12} {w['name'][:20]:20} ({len(w['nodes'])} nodes)")
    print(f"  Green: {len(parsed['green'])}")
    for g in parsed["green"][:3]:
        print(f"    {g['kind']:12} {g['name'][:20]:20} ({len(g['nodes'])} nodes)")
else:
    print("  FAILED")

# 测试 2: 高德 place_around
print()
print("=" * 60)
print("[2] 高德 place_around: 天安门 500m")
print("=" * 60)
pois = amap.place_around((116.397, 39.909), radius=500)
print(f"  Got {len(pois)} POIs")
for p in pois[:5]:
    print(f"    {p['name']:30} {p['type']:20} {p['distance']}m")

# 测试 3: bbox 工具
print()
print("=" * 60)
print("[3] bbox 工具")
print("=" * 60)
pts = [(39.909, 116.397), (39.911, 116.400), (39.910, 116.402)]
bbox = compute_bbox_from_points(pts, pad_ratio=0.1)
print(f"  compute_bbox_from_points: {bbox}")
expanded = expand_bbox(bbox, min_size_deg=0.008)
print(f"  expand to 0.008°:         {expanded}")
h_deg = expanded[2] - expanded[0]
w_deg = expanded[3] - expanded[1]
# 1° lat ≈ 111km, 1° lng @ 40° ≈ 85km
h_m = h_deg * 111000
w_m = w_deg * 85000
print(f"  size: {h_m:.0f}m x {w_m:.0f}m")
