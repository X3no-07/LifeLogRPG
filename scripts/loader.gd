extends RefCounted
class_name LogLoader
# LogLoader - 严格解析 baker 输出的 JSON
# 配套 baker/core/schema.py, 任何字段名/类型变更必须同步更新
#
# 公开 API:
#   load(path: String) -> Dictionary   # 主入口, 失败返回 {}
#   get_waypoints() -> Array
#   get_dialogs() -> Array
#   get_map() -> Dictionary
#   get_meta() -> Dictionary
#   get_total_duration() -> float
#   get_pois() -> Array                 # P0.3
#   get_transit_markers() -> Array      # P0.4
#
# 容错策略:
#   - 缺字段: 用默认值, 打印 warning
#   - 类型错: 强转, 打印 warning
#   - 文件不存在/解析失败: 返回 {}

const SCHEMA_VERSION: int = 1

var _raw: Dictionary = {}
var _waypoints: Array = []
var _dialogs: Array = []
var _map: Dictionary = {}
var _meta: Dictionary = {}
var _pois: Array = []
var _transit_markers: Array = []   # P0.4
var _building_heights: Array = []   # P1.2 (跟 grid 同步, 0=无建筑)
var _interiors: Array = []          # P1.3 (室内 slot: 咖啡厅/办公室/etc.)
var _stops: Array[Dictionary] = []
var _log_path: String = ""          # P1.4 本次加载的 JSON 路径 (派生渲染图路径)


func load(path: String) -> Dictionary:
    """主入口, 加载并校验, 返回整个 payload dict (供其他模块直接读)"""
    _log_path = path
    _raw = {}
    _waypoints = []
    _dialogs = []
    _map = {}
    _meta = {}
    _pois = []
    _transit_markers = []
    _building_heights = []
    _interiors = []
    _stops.clear()

    if not FileAccess.file_exists(path):
        push_error("LogLoader: file not found: " + path)
        return {}
    var f := FileAccess.open(path, FileAccess.READ)
    if f == null:
        push_error("LogLoader: cannot open: " + path)
        return {}
    var txt := f.get_as_text()
    f.close()
    var json := JSON.new()
    if json.parse(txt) != OK:
        push_error("LogLoader: JSON parse error at %s: %s" % [path, json.get_error_message()])
        return {}

    _raw = json.data
    _validate(_raw)
    _load_stops(_raw.get("stops", []))
    return _raw


func _validate(payload: Dictionary) -> void:
    """强校验 + 默认值填充, 打印 warning 不阻断"""
    # 顶层 keys
    for required_key in ["meta", "map", "path", "dialogs"]:
        if not payload.has(required_key):
            push_warning("LogLoader: missing key '%s', using default" % required_key)

    _meta = payload.get("meta", {})
    _map = payload.get("map", {})
    _waypoints = payload.get("path", [])
    _dialogs = payload.get("dialogs", [])
    _pois = payload.get("pois", [])
    _transit_markers = payload.get("transit_markers", [])
    # P1.2: building_heights 在 map 子层, 不是顶层
    _building_heights = _map.get("building_heights", [])
    # P1.3: interiors 顶层字段
    _interiors = payload.get("interiors", [])

    # map 字段
    if not _map.has("tile_size"):
        _map["tile_size"] = 16
    if not _map.has("width"):
        _map["width"] = 80
    if not _map.has("height"):
        _map["height"] = 60
    if not _map.has("grid"):
        _map["grid"] = []

    # waypoints 校验 (每条必须有 x/y/t/transport)
    for i in range(_waypoints.size()):
        var wp: Dictionary = _waypoints[i]
        if not wp.has("x") or not wp.has("y"):
            push_warning("LogLoader: waypoint[%d] missing x/y, removed" % i)
            _waypoints[i] = {}
            continue
        if not wp.has("t"):
            wp["t"] = 0.0
        if not wp.has("transport"):
            wp["transport"] = "walking"
        if not wp.has("label"):
            wp["label"] = ""

    # dialogs 校验
    for i in range(_dialogs.size()):
        var d: Dictionary = _dialogs[i]
        if not d.has("t"):
            d["t"] = 0.0
        if not d.has("speaker"):
            d["speaker"] = "Me"
        if not d.has("text"):
            d["text"] = ""

    # P0.3 POI 校验
    for i in range(_pois.size()):
        var poi: Dictionary = _pois[i]
        for k in ["name", "type", "category", "address"]:
            if not poi.has(k):
                poi[k] = ""
        for k in ["lng", "lat", "distance"]:
            if not poi.has(k):
                poi[k] = 0
        for k in ["grid_x", "grid_y"]:
            if not poi.has(k):
                poi[k] = 0

    # P0.4 TransitMarker 校验
    for i in range(_transit_markers.size()):
        var tm: Dictionary = _transit_markers[i]
        if not tm.has("name"):
            tm["name"] = ""
        if not tm.has("transport"):
            tm["transport"] = "transit"
        for k in ["start_lng", "start_lat", "end_lng", "end_lat",
                  "distance_m", "duration_sec"]:
            if not tm.has(k):
                tm[k] = 0.0
        for k in ["start_grid_x", "start_grid_y", "end_grid_x", "end_grid_y"]:
            if not tm.has(k):
                tm[k] = -1   # -1 表示超出 grid, Godot 端决定是否画边缘 pin


func _load_stops(raw_stops: Variant) -> void:
    var duration := get_total_duration()
    if raw_stops is Array:
        for item in raw_stops:
            if not item is Dictionary:
                continue
            var valid_numbers := true
            for key in ["x", "y", "t"]:
                if typeof(item.get(key)) not in [TYPE_INT, TYPE_FLOAT]:
                    valid_numbers = false
                    break
            if not valid_numbers:
                continue
            var x := float(item["x"])
            var y := float(item["y"])
            var time := float(item["t"])
            if not (x >= 0 and x < get_grid_width() and y >= 0 and y < get_grid_height()):
                continue
            if not (time >= 0 and time <= duration + 0.001):
                continue
            _stops.append(item)
    if not _stops.is_empty() or _waypoints.is_empty():
        return

    # 旧存档只记录了路线。沿用明确的终点名称或显示通用终点。
    var endpoint: Dictionary = _waypoints[-1]
    if not endpoint.has("x") or not endpoint.has("y"):
        return
    var label := String(endpoint.get("label", "")).strip_edges()
    label = label.trim_suffix("_arrive")
    for prefix in ["pt_", "step_"]:
        if label.begins_with(prefix):
            label = ""
            break
    _stops.append({"x": endpoint["x"], "y": endpoint["y"], "t": duration, "name": label})


# ----- 访问器 -----

func get_waypoints() -> Array:
    return _waypoints

func get_dialogs() -> Array:
    return _dialogs

func get_map() -> Dictionary:
    return _map

func get_log_meta() -> Dictionary:
    """返回日志的 meta 段 (注意: 跟 Node.get_meta() 命名冲突, 显式加 log_ 前缀)"""
    return _meta

func get_pois() -> Array:
    """返回 POI 列表 (P0.3 新增)"""
    return _pois


func get_stops() -> Array[Dictionary]:
    return _stops

func get_transit_markers() -> Array:
    """返回 TransitMarker 列表 (P0.4 新增)
    每条: {name, transport, start_lng, start_lat, end_lng, end_lat,
           start_grid_x, start_grid_y, end_grid_x, end_grid_y,
           distance_m, duration_sec}
    """
    return _transit_markers

func get_building_heights() -> Array:
    """返回 building_heights 二维数组 (P1.2 新增)
    building_heights[y][x] = 0 (无建筑) 或 N (N 层)
    跟 grid 同步大小
    """
    return _building_heights

func get_interiors() -> Array:
    """返回 interior slot 列表 (P1.3 新增)
    每条: {name, category, raw_tag, lng, lat, grid_x, grid_y, has_name}
    画在对应 building 中心 cell 上, 用 interior_<category> icon
    """
    return _interiors

func get_tile_size() -> int:
    return int(_map.get("tile_size", 16))

func get_grid_width() -> int:
    return int(_map.get("width", 80))

func get_grid_height() -> int:
    return int(_map.get("height", 60))

func get_grid() -> Array:
    return _map.get("grid", [])

func get_total_duration() -> float:
    if _waypoints.is_empty():
        return 0.0
    return float(_waypoints[-1].get("t", 0.0))

func get_log_title() -> String:
    return String(_meta.get("title", ""))

func get_log_path() -> String:
    """本次加载的 JSON 路径 (P1.4 新增)"""
    return _log_path

func get_map_image_path() -> String:
    """baker 渲染图路径 (P1.4 新增): JSON 同目录同名, 后缀 _map.png
    例: res://saved_logs/test_palace.json -> res://saved_logs/test_palace_map.png
    没加载过 / 不是 .json 结尾返回 "" (调用方回退到 TileMap)"""
    if _log_path == "" or not _log_path.ends_with(".json"):
        return ""
    return _log_path.substr(0, _log_path.length() - 5) + "_map.png"
