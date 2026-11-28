"""运行桌面启动器提交的烘焙任务，任务参数与结果通过本地文件传递。"""

import json
import math
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class LauncherError(Exception):
    """可以直接在启动器中显示的提示。"""


def _read_request(path: Path) -> Dict[str, Any]:
    try:
        contents = path.read_text(encoding="utf-8-sig")
    finally:
        path.unlink(missing_ok=True)

    try:
        request = json.loads(contents)
    except json.JSONDecodeError:
        raise LauncherError("读取生成任务失败，请重新提交。") from None
    if not isinstance(request, dict):
        raise LauncherError("读取生成任务失败，请重新提交。")
    return request


def _coords(value: str) -> str:
    format_error = "请输入至少两个不同的坐标，格式为经度,纬度，坐标之间用分号或换行分隔。"
    points = []
    for pair in re.split(r"[;；\r\n]+", value):
        if not pair.strip():
            continue
        try:
            lng, lat = (float(part) for part in pair.replace("，", ",").split(","))
        except ValueError:
            raise LauncherError(format_error) from None
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise LauncherError("坐标超出范围。请输入经度 -180 至 180、纬度 -90 至 90。")
        points.append((lng, lat))
    if len(set(points)) < 2:
        raise LauncherError(format_error)
    return ";".join(f"{lng},{lat}" for lng, lat in points)


def _api_key(request: Dict[str, Any], config: Dict[str, Any], provider: str) -> str:
    submitted = request.get(f"{provider}_key", "")
    if not isinstance(submitted, str):
        raise LauncherError("无法读取接口配置，请重新输入 Key。")
    key = str(submitted.strip() or config[provider].get("api_key") or "").strip()
    return "" if key.startswith("YOUR_") else key


def _selected_places(request: Dict[str, Any]) -> list:
    places = request.get("selected_places", [])
    if places == []:
        return []
    if isinstance(places, list) and len(places) == 2 and all(
        isinstance(place, dict)
        and isinstance(place.get("name"), str) and 0 < len(place["name"]) <= 200
        and type(place.get("lng")) in (float, int) and -180 <= place["lng"] <= 180
        and type(place.get("lat")) in (float, int) and -90 <= place["lat"] <= 90
        for place in places
    ):
        if (places[0]["lng"], places[0]["lat"]) != (places[1]["lng"], places[1]["lat"]):
            return places
        raise LauncherError("起点和终点重合，请重新选择。")
    raise LauncherError("请从候选列表重新选择起点和终点。")


def _suggest(request: Dict[str, Any]) -> list:
    from .clients.amap import AmapClient
    from .config import load_config

    config = load_config()
    key = _api_key(request, config, "amap")
    if not key:
        raise LauncherError("请先输入高德 Web 服务 Key，再搜索地点。")
    city = request.get("city", "").strip() or config["bake"]["default_city"]
    query = request.get("query", "").strip()
    if not query or len(query) > 120 or len(city) > 64:
        raise LauncherError("请输入简短的城市和地点名称。")
    city_name = city.removesuffix("市")
    if city_name and query.startswith(city_name):
        query = query.removeprefix(city_name).removeprefix("市") or query
    try:
        return AmapClient(key, config["amap"]["base_url"], timeout=4).suggest_places(query, city)
    except OSError:
        raise LauncherError("高德搜索暂时不可用，请检查网络、Web 服务 Key 或额度。") from None


def _bake(request: Dict[str, Any], progress: Callable[[str], None]) -> Path:
    mode = request.get("mode")
    text = request.get("input")
    duration = request.get("duration", 30)
    output = request.get("output_dir")
    if mode not in ("coords", "text") or not isinstance(text, str) or not text.strip():
        raise LauncherError("请先输入坐标或日记。")
    if (type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
        raise LauncherError("请输入有效的回放时长。")
    if not isinstance(output, str) or not Path(output).is_absolute():
        raise LauncherError("无法定位回放目录，请重启应用后再试。")
    if mode == "coords":
        text = _coords(text)

    # 导入放在任务边界内，依赖缺失时也能清理请求并把错误返回给启动器。
    from .config import load_config
    from .core.time_scale import apply_time_scale
    from .modes import CoordsMode, TextMode
    from .modes.text import PlaceResolutionError

    config = load_config()
    config["amap"]["api_key"] = _api_key(request, config, "amap")
    config["amap"]["timeout_sec"] = 8
    config["bake"]["output_dir"] = output
    config["bake"]["osm_timeout_sec"] = 12
    config["bake"]["fuzzy_candidate_limit"] = 8
    if mode == "text":
        city = request.get("city", "")
        if not isinstance(city, str) or len(city) > 64:
            raise LauncherError("请输入有效的城市名称。")
        if city.strip():
            config["bake"]["default_city"] = city.strip()
        config["deepseek"]["api_key"] = _api_key(request, config, "deepseek")
        config["deepseek"]["timeout_sec"] = 20
        if not config["amap"]["api_key"] or not config["deepseek"]["api_key"]:
            raise LauncherError("日记模式需要高德 Web 服务 Key 和 DeepSeek API Key。")
        config["bake"]["llm_provider"] = "deepseek"
        generator = TextMode("route", text, config)
        generator.selected_places = _selected_places(request)
    else:
        generator = CoordsMode("route", text, config)

    generator.progress_callback = progress
    try:
        payload = generator.run()
    except PlaceResolutionError as error:
        raise LauncherError(str(error)) from None
    except SystemExit as error:
        if mode == "text" and error.code == 2:
            raise LauncherError("没能识别两个地点。请写清出发地和目的地，并检查 DeepSeek Key。") from None
        if mode == "text" and error.code in (3, 4):
            raise LauncherError("没能定位日记里的地点。请写清城市和地名，并检查高德 Key。") from None
        raise LauncherError("没能生成路线，请检查输入的地点或坐标。") from None

    osm = (generator._render_ctx or {}).get("osm") or {}
    if not osm.get("roads"):
        raise LauncherError("无法取得这片区域的 OpenStreetMap 路网。请检查网络，或换一组坐标。")
    if len(payload.path) < 2 or payload.path[-1].t <= 0:
        raise LauncherError("没能找到可回放的路线。请将出发地和目的地设得远一些。")

    if duration > 0:
        apply_time_scale(payload, duration)
    progress("render")
    log_path = generator.write()
    if not log_path.with_name(f"{log_path.stem}_map.png").is_file():
        raise LauncherError("地图图片生成失败，请重新生成。")
    return log_path


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def main(argv: Optional[list] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2) or not all(Path(path).is_absolute() for path in args):
        return 2
    request_path = Path(args[0])
    result_path = request_path.with_name("result.json")
    progress_path = request_path.with_name("progress.json")

    def progress(stage: str) -> None:
        try:
            _write_json(progress_path, {"stage": stage})
        except PermissionError:
            # Windows can briefly lock the destination while the launcher reads it.
            pass

    try:
        request = _read_request(request_path)
        if len(args) == 2 and sys.platform == "win32":
            from .local_keys import remember_keys
            try:
                remember_keys(Path(args[1]), request)
            except OSError:
                pass
        # 上游接口日志可能包含用户日记或请求信息，桌面模式只传递安全的摘要。
        with open(os.devnull, "w", encoding="utf-8") as quiet:
            with redirect_stdout(quiet), redirect_stderr(quiet):
                if request.get("mode") == "suggest":
                    result = {"ok": True, "choices": _suggest(request)}
                else:
                    log_path = _bake(request, progress)
                    result = {"ok": True, "message": "路线已生成，可以回放。", "log_path": str(log_path)}
    except LauncherError as error:
        result = {"ok": False, "message": str(error), "log_path": ""}
    except ImportError:
        result = {"ok": False, "message": "缺少地图生成组件，请重新解压应用。", "log_path": ""}
    except Exception:
        result = {"ok": False, "message": "路线生成失败。请检查网络和输入后重试。", "log_path": ""}

    _write_json(result_path, result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
