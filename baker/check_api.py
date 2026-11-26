#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Life Log RPG - API 连通性测试
==============================
验证 config.json 里的高德 Key 和 MiniMax Key 都能用, 避免直接跑 bake.py 卡住。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_amap(api_key: str, base_url: str = "https://restapi.amap.com/v3") -> bool:
    """测试高德 geocode API"""
    import requests
    print("\n[1] 高德 geocode API")
    print("-" * 50)
    try:
        r = requests.get(
            f"{base_url}/geocode/geo",
            params={"key": api_key, "address": "北京天安门", "output": "JSON"},
            timeout=10,
        )
        data = r.json()
        status = data.get("status")
        info = data.get("info", "")
        if status == "1" and data.get("geocodes"):
            loc = data["geocodes"][0]["location"]
            print(f"  ✓ 状态: {status} ({info})")
            print(f"  ✓ 北京天安门 -> {loc} (lng,lat)")
            return True
        else:
            print(f"  ✗ 状态: {status} ({info})")
            print(f"  完整返回: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
            return False
    except Exception as e:
        print(f"  ✗ 异常: {e}")
        return False


def test_amap_route(api_key: str, base_url: str = "https://restapi.amap.com/v3") -> bool:
    """测试高德路径规划 API"""
    import requests
    print("\n[2] 高德 walking 路径规划")
    print("-" * 50)
    try:
        r = requests.get(
            f"{base_url}/direction/walking",
            params={
                "key": api_key,
                "origin": "116.397,39.909",  # 天安门
                "destination": "116.408,39.918",  # 王府井
                "output": "JSON",
            },
            timeout=10,
        )
        data = r.json()
        status = data.get("status")
        info = data.get("info", "")
        if status == "1" and data.get("route", {}).get("paths"):
            path = data["route"]["paths"][0]
            print(f"  ✓ 状态: {status} ({info})")
            print(f"  ✓ 距离: {path.get('distance')} m, 耗时: {path.get('duration')} s")
            polyline = path.get("polyline", "")
            pts = polyline.split(";") if polyline else []
            print(f"  ✓ 路径点数: {len(pts)}")
            return True
        else:
            print(f"  ✗ 状态: {status} ({info})")
            print(f"  完整返回: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
            return False
    except Exception as e:
        print(f"  ✗ 异常: {e}")
        return False


def test_minimax(api_key: str, group_id: str, base_url: str = "https://api.minimaxi.com/v1",
                 model: str = "MiniMax-M3.1-Flash") -> bool:
    """测试 MiniMax 文本生成 API"""
    import requests
    print(f"\n[3] MiniMax 文本 API (model={model})")
    print("-" * 50)
    if not group_id:
        print(f"  ⚠ group_id 为空, 尝试不带 group_id 调一下看错误信息")
    url = f"{base_url}/text/chatcompletion_v2"
    if group_id:
        url += f"?groupId={group_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "用一句话说'你好'"}],
        "max_tokens": 50,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        data = r.json()
        if "choices" in data and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content", "")
            print(f"  ✓ HTTP {r.status_code}")
            print(f"  ✓ 模型回复: {content[:200]}")
            return True
        else:
            print(f"  ✗ HTTP {r.status_code}")
            print(f"  返回: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
            return False
    except Exception as e:
        print(f"  ✗ 异常: {e}")
        return False


def main():
    config = load_config()
    amap_key = config.get("amap", {}).get("api_key", "")
    amap_base = config.get("amap", {}).get("base_url", "https://restapi.amap.com/v3")
    mm_key = config.get("minimax", {}).get("api_key", "")
    mm_group = config.get("minimax", {}).get("group_id", "")
    mm_base = config.get("minimax", {}).get("base_url", "https://api.minimaxi.com/v1")
    mm_model = config.get("minimax", {}).get("text_model", "MiniMax-M3.1-Flash")

    print("=" * 60)
    print("Life Log RPG - API 连通性测试")
    print("=" * 60)
    print(f"高德 Key: {amap_key[:6]}...{amap_key[-4:]} ({'已填' if amap_key else '空'})")
    print(f"MiniMax Key: {mm_key[:10]}...{mm_key[-4:]} ({'已填' if mm_key else '空'})")
    print(f"MiniMax group_id: '{mm_group}' ({'已填' if mm_group else '空'})")

    results = []
    if amap_key:
        results.append(("高德 geocode", test_amap(amap_key, amap_base)))
        results.append(("高德 walking 路径", test_amap_route(amap_key, amap_base)))
    else:
        print("\n[!] 高德 Key 为空, 跳过")
    if mm_key:
        results.append(("MiniMax 文本", test_minimax(mm_key, mm_group, mm_base, mm_model)))
    else:
        print("\n[!] MiniMax Key 为空, 跳过")

    print("\n" + "=" * 60)
    print("汇总:")
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print("=" * 60)
    sys.exit(0 if all(ok for _, ok in results) else 1)


if __name__ == "__main__":
    main()
