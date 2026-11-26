"""Baker 配置读取

从 F:\\LifeLogRPG_Project\\config.json 读 API Key 和参数。
任何 .gd / .cs / .py 严禁硬编码 Key, 一律走本模块。
"""
import json
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """读 config.json, 不存在时返回硬编码默认值
    不会抛异常, 这样 P0 demo 阶段可以无 Key 跑通 (API 调用时返回 None 即可)
    """
    if not path.exists():
        print(f"[config] WARN: {path} 不存在, 用默认空配置")
        return _default_config()
    try:
        # 用 utf-8-sig 兼容 BOM (PowerShell Set-Content 默认加 BOM)
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[config] ERROR: 解析 {path} 失败: {e}")
        return _default_config()


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
