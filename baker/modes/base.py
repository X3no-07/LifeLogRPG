"""Mode 抽象基类"""
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from ..core.schema import LogPayload, Meta, MapData, Waypoint, Dialog, Character
from ..config import load_config, get_output_dir


class BaseMode(ABC):
    """所有 mode 必须实现 run() -> LogPayload"""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or load_config()
        self.payload = self._empty_payload()
        self.progress_callback: Optional[Callable[[str], None]] = None
        # 火红渲染上下文 (text/coords 模式在 run() 末尾填):
        # {"bbox", "osm", "start_name", "end_name"}; 没填就不画图。
        self._render_ctx: Optional[Dict[str, Any]] = None

    def report_progress(self, stage: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(stage)

    def _empty_payload(self) -> LogPayload:
        """构造一个空白 payload, 子类填充"""
        meta = Meta(
            log_id=self.name,
            title="",
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        bake_cfg = self.config.get("bake", {})
        grid_w = int(bake_cfg.get("viewport_grid_w", 320))
        grid_h = int(bake_cfg.get("viewport_grid_h", 240))
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
        """把 payload 写入 saved_logs/{name}.json, 再自动画火红地图
        (saved_logs/{name}_map.png, 跟 JSON 同名不同后缀)。
        渲染失败不丢 JSON: 记日志、返回 JSON 路径, 烘焙本身算成功。"""
        import json
        out_path = self.get_output_path(suffix)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.payload.to_dict(), f, ensure_ascii=False, indent=2)
        p = self.payload
        print(f"[done] saved to {out_path}")
        print(f"       waypoints: {len(p.path)}, dialogs: {len(p.dialogs)}, "
              f"map: {p.map.width}x{p.map.height}")
        self.render_map()
        return out_path

    def render_map(self) -> Optional["Path"]:
        """按 _render_ctx 画火红地图, 存到 saved_logs/{name}_map.png。
        成功返回图路径, 没上下文返回 None, 失败记日志返回 None
        (绝不抛异常: 烘焙主流程不能因画图挂掉)。"""
        from pathlib import Path
        ctx = getattr(self, "_render_ctx", None)
        if not ctx:
            return None
        try:
            from ..render import render_firered_map
            p = self.payload
            out_path = self.get_output_path("_map.png")
            render_firered_map(
                grid=p.map.grid,
                building_heights=p.map.building_heights or None,
                path=[{"x": w.x, "y": w.y, "transport": w.transport}
                      for w in p.path],
                pois=[{"name": poi.name, "grid_x": poi.grid_x,
                       "grid_y": poi.grid_y,
                       "category": getattr(poi, "category", "")}
                      for poi in p.pois],
                osm=ctx.get("osm"),
                bbox=ctx.get("bbox"),
                output_path=out_path,
                start_name=ctx.get("start_name", ""),
                end_name=ctx.get("end_name", ""),
            )
            print(f"[done] map saved to {out_path}")
            return out_path
        except Exception as e:
            import traceback
            print(f"[render] WARN: 火红地图渲染失败, JSON 不受影响: {e}")
            traceback.print_exc()
            return None
