"""Baker 配置读取

优先级 (后者覆盖前者):
1. config.json (入库, key 是占位符)
2. config.local.json (gitignored, 放真实 key, 只写要覆盖的字段)
3. 环境变量 LIFELOG_AMAP_KEY / LIFELOG_MINIMAX_KEY (最高, 供 CI / 安全存储注入)
任何 .gd / .cs / .py 严禁硬编码 Key, 一律走本模块。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
LOCAL_CONFIG_NAME = "config.local.json"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并: override 只覆盖它写明的字段, 其余保留 base 的。
    这样 config.local.json 只用写 {"amap": {"api_key": "..."}} 即可。
    """
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_json_file(path: Path) -> Dict[str, Any]:
    """读一个 JSON 配置, 失败返回空 dict (不抛异常)。"""
    if not path.exists():
        return {}
    try:
        # 用 utf-8-sig 兼容 BOM (PowerShell Set-Content 默认加 BOM)
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[config] ERROR: 解析 {path} 失败: {e}")
        return {}


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """读 config.json, 再用 config.local.json 和环境变量覆盖。
    不会抛异常, 这样 P0 demo 阶段可以无 Key 跑通 (API 调用时返回 None 即可)
    """
    if not path.exists():
        print(f"[config] WARN: {path} 不存在, 用默认空配置")
        config = _default_config()
    else:
        config = _deep_merge(_default_config(), _load_json_file(path))
    # 2) config.local.json (gitignored) 覆盖, 只写要改的字段
    local_path = Path(path).parent / LOCAL_CONFIG_NAME
    local = _load_json_file(local_path)
    if local:
        config = _deep_merge(config, local)
    # 3) 环境变量覆盖 (最高优先级)
    amap_key = os.environ.get("LIFELOG_AMAP_KEY", "").strip()
    if amap_key:
        config.setdefault("amap", {})["api_key"] = amap_key
    minimax_key = os.environ.get("LIFELOG_MINIMAX_KEY", "").strip()
    if minimax_key:
        config.setdefault("minimax", {})["api_key"] = minimax_key
    return config


def _default_config() -> Dict[str, Any]:
    return {
        "amap": {"api_key": "", "base_url": "https://restapi.amap.com/v3", "timeout_sec": 10},
        "minimax": {
            "api_key": "", "group_id": "", "base_url": "https://api.minimaxi.com/v1",
            "text_model": "MiniMax-M3.1-Flash", "vision_model": "abab6.5s-chat", "timeout_sec": 30,
        },
        "bake": {
            "output_dir": str(PROJECT_ROOT / "saved_logs"),
            "tile_size_px": 16, "viewport_grid_w": 160, "viewport_grid_h": 120,
            "default_city": "北京", "weather_seed": 42,
        },
        "playback": {"default_speed": 1.0, "min_speed": 0.25, "max_speed": 8.0},
    }


def get_amap_key(config: Dict[str, Any]) -> str:
    return config.get("amap", {}).get("api_key", "")


def get_minimax_key(config: Dict[str, Any]) -> str:
    return config.get("minimax", {}).get("api_key", "")


def get_minimax_group(config: Dict[str, Any]) -> str:
    return config.get("minimax", {}).get("group_id", "")


def get_output_dir(config: Dict[str, Any]) -> Path:
    out = config.get("bake", {}).get("output_dir", str(PROJECT_ROOT / "saved_logs"))
    p = Path(out)
    # config 里写相对路径时, 以项目根目录为准 (不要随启动时的 cwd 跑偏)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p
