"""Mode 抽象基类"""
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..core.schema import LogPayload, Meta, MapData, Waypoint, Dialog, Character
from ..config import load_config, get_output_dir


class BaseMode(ABC):
    """所有 mode 必须实现 run() -> LogPayload"""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or load_config()
        self.payload = self._empty_payload()

    def _empty_payload(self) -> LogPayload:
        """构造一个空白 payload, 子类填充"""
        meta = Meta(
            log_id=self.name,
            title="",
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        bake_cfg = self.config.get("bake", {})
        grid_w = int(bake_cfg.get("viewport_grid_w", 80))
        grid_h = int(bake_cfg.get("viewport_grid_h", 60))
        tile_size = int(bake_cfg.get("tile_size_px", 16))
        map_data = MapData(tile_size=tile_size, width=grid_w, height=grid_h, grid=[])
        payload = LogPayload(meta=meta, map=map_data)
        payload.characters.append(Character())
        return payload

    @abstractmethod
    def run(self) -> LogPayload:
        """子类实现: 填充 self.payload 并返回"""
        ...

    def get_output_path(self, suffix: str = ".json") -> "Path":
        from pathlib import Path
        out_dir = get_output_dir(self.config)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{self.name}{suffix}"

    def write(self, suffix: str = ".json") -> "Path":
        """把 payload 写入 saved_logs/{name}.json"""
        import json
        out_path = self.get_output_path(suffix)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.payload.to_dict(), f, ensure_ascii=False, indent=2)
        p = self.payload
        print(f"[done] saved to {out_path}")
        print(f"       waypoints: {len(p.path)}, dialogs: {len(p.dialogs)}, "
              f"map: {p.map.width}x{p.map.height}")
        return out_path
