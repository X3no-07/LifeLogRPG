"""Mock 模式: 用预定义数据, 不需要 API Key

适合 P0 demo 和单元测试。
"""
from typing import List

from ..core.gridifier import build_grid_from_waypoints
from ..core.schema import Waypoint, Dialog
from .base import BaseMode


class MockMode(BaseMode):
    """320x240 grid + 直线+拐弯路径, 5 条对话"""

    PATH_PIXELS = [
        (5, 10), (10, 10), (15, 10), (20, 10), (25, 10),
        (25, 15), (25, 20), (25, 25), (25, 30),
        (30, 30), (40, 30), (50, 30), (60, 30),
        (60, 35), (60, 40), (60, 45), (60, 50),
        (65, 50), (70, 50), (75, 50),
    ]
    TRANSPORT_BREAKS = {5: "transit", 9: "transit", 13: "walking"}
    DIALOGS = [
        (4.0, "Me", "出门, 天气不错"),
        (12.0, "路人", "早! 赶着去上班呢"),
        (18.0, "Me", "挤地铁中..."),
        (28.0, "同事", "老张! 这边这边"),
        (35.0, "老张", "走, 中午请你吃饭"),
    ]

    def run(self) -> "LogPayload":
        p = self.payload
        p.meta.title = "Mock 日志 - 城市漫游"
        p.meta.weather = "sunny"
        p.meta.mood = "happy"
        p.meta.bgm = "town01.mid"

        # 路径 (mock 模式 1 grid = 1 px)
        waypoints_grid = [{"x": x, "y": y} for (x, y) in self.PATH_PIXELS]
        # 时间戳按累计路程分 (匀速走): 每点固定 1.5s 会让 5 格段和 10 格段
        # 速度差一倍 (53 vs 107 px/s), 人物忽快忽慢; 跟 text.py 同一个约定,
        # 用 bake.default_walk_speed_px_per_sec (60 px/s) 匀速走。
        walk_speed = float(self.config.get("bake", {}).get(
            "default_walk_speed_px_per_sec", 60.0))
        step_px = float(self.config.get("bake", {}).get("tile_size_px", 16))
        cum_dist = 0.0
        prev = None
        for i, wp in enumerate(waypoints_grid):
            if prev is not None:
                cum_dist += ((wp["x"] - prev["x"]) ** 2
                             + (wp["y"] - prev["y"]) ** 2) ** 0.5 * step_px
            transport = self.TRANSPORT_BREAKS.get(i, "walking")
            p.path.append(Waypoint(
                x=wp["x"], y=wp["y"], t=cum_dist / walk_speed,
                label=f"step_{i}", transport=transport,
            ))
            prev = wp

        # 网格 (路上 1, 草地 0, 树 4, 建筑 2)
        p.map.grid = build_grid_from_waypoints(waypoints_grid, p.map.width, p.map.height)

        # 对话
        for (t, sp, text) in self.DIALOGS:
            p.dialogs.append(Dialog(t=t, speaker=sp, text=text))

        # 火红渲染上下文: write() 时自动画地图。Mock 没有真实 OSM/bbox,
        # 只按网格画 (渲染器 osm/bbox 为空时降级画网格, 不报错);
        # 没上下文就不出图, Godot 会回退到 TileMap 色块。
        self._render_ctx = {
            "bbox": None,
            "osm": None,
            "start_name": "",
            "end_name": "",
        }

        return p
