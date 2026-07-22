"""P0.4 最终验证 (单次运行)"""
import json
import sys

log_path = sys.argv[1] if len(sys.argv) > 1 else "saved_logs/log_v2_text.json"
d = json.load(open(log_path, encoding="utf-8-sig"))

print(f"=== P0.4 自适应切片验证 ({log_path}) ===")
print(f"  Map: {d['map']['width']}x{d['map']['height']}")
print(f"  Path waypoints: {len(d['path'])}")
print(f"  POI: {len(d['pois'])}")
print(f"  Transit markers: {len(d['transit_markers'])}")
for tm in d["transit_markers"]:
    name = tm["name"]
    transport = tm["transport"]
    dist = tm["distance_m"] / 1000
    dur = tm["duration_sec"]
    sgx, sgy = tm["start_grid_x"], tm["start_grid_y"]
    egx, egy = tm["end_grid_x"], tm["end_grid_y"]
    print(f"    - {name} ({transport}) {dist:.1f}km / {dur:.0f}s")
    print(f"      grid: ({sgx},{sgy}) -> ({egx},{egy})")
    if egx in (0, 79) or egy in (0, 59):
        print("      [端点] clamp 到 grid 边缘")
print()
print("  Path 时间线:")
print(f"    t=0..{d['path'][-2]['t']:.0f}s: {d['path'][-2]['transport']} ({d['path'][-2]['label']})")
print(f"    t={d['path'][-1]['t']:.0f}s: {d['path'][-1]['transport']} ({d['path'][-1]['label']})")
