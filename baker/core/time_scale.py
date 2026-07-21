"""时间缩放 (P1.5)

把 waypoint / dialog 的 t 等比例压缩到目标时长。
例: 真实 1h 步行 -> 朋友圈 30s 视频, 压缩 120x。
"""
from typing import Any, Dict, List, Union

from .schema import LogPayload


PayloadType = Union[LogPayload, Dict[str, Any]]


def apply_time_scale(payload: PayloadType, target_duration: float) -> None:
    """原地修改 payload, 把 path[*].t 和 dialogs[*].t 等比例缩放到 target_duration 秒
    payload 可以是 LogPayload (新接口) 或 dict (兼容旧调用)
    """
    if target_duration <= 0:
        return
    if isinstance(payload, LogPayload):
        return _apply_to_obj(payload, target_duration)
    return _apply_to_dict(payload, target_duration)


def _apply_to_obj(payload: LogPayload, target_duration: float) -> None:
    if not payload.path:
        return
    max_t = max((wp.t for wp in payload.path), default=0)
    if max_t <= 0:
        return
    scale = target_duration / max_t
    for wp in payload.path:
        wp.t = round(wp.t * scale, 2)
    for dlg in payload.dialogs:
        dlg.t = round(dlg.t * scale, 2)
    payload.meta.original_duration_sec = max_t
    payload.meta.scaled_duration_sec = target_duration
    print(f"[time_scale] {max_t:.1f}s -> {target_duration:.1f}s (压缩 {1/scale:.1f}x)")


def _apply_to_dict(payload: Dict[str, Any], target_duration: float) -> None:
    waypoints: List[Dict[str, Any]] = payload.get("path", [])
    if not waypoints:
        return
    max_t = max((wp.get("t", 0) for wp in waypoints), default=0)
    if max_t <= 0:
        return
    scale = target_duration / max_t
    for wp in waypoints:
        wp["t"] = round(wp.get("t", 0) * scale, 2)
    for dlg in payload.get("dialogs", []):
        if "t" in dlg:
            dlg["t"] = round(dlg["t"] * scale, 2)
    meta = payload.setdefault("meta", {})
    meta["original_duration_sec"] = max_t
    meta["scaled_duration_sec"] = target_duration
    print(f"[time_scale] {max_t:.1f}s -> {target_duration:.1f}s (压缩 {1/scale:.1f}x)")


def normalize_dialog_times(dialogs: List[Dict[str, Any]], total_duration: float) -> List[Dict[str, Any]]:
    """把 LLM 输出的 t_offset (0-1) 转成实际秒数 t
    兼容三种输入:
    - {"t_offset": 0.0~1.0}
    - {"t": 0~N 秒}
    - 都没有 -> 均匀分配
    """
    if not dialogs:
        return []
    n = len(dialogs)
    has_offset = any("t_offset" in d for d in dialogs)
    has_t = any("t" in d for d in dialogs)
    out: List[Dict[str, Any]] = []
    for i, d in enumerate(dialogs):
        nd = dict(d)
        if has_offset and "t_offset" in d:
            nd["t"] = float(d["t_offset"]) * total_duration
        elif has_t and "t" in d:
            nd["t"] = float(d["t"])
        else:
            ratio = (i / max(n - 1, 1)) * 0.95
            nd["t"] = ratio * total_duration
        nd.pop("t_offset", None)
        out.append(nd)
    return out

