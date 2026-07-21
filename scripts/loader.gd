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


func load(path: String) -> Dictionary:
    """主入口, 加载并校验, 返回整个 payload dict (供其他模块直接读)"""
    _raw = {}
    _waypoints = []
    _dialogs = []
    _map = {}
    _meta = {}

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
