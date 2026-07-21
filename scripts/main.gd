extends Node2D
@warning_ignore("inferred_declaration", "untyped_declaration", "unsafe_property_access",
              "unsafe_method_access", "unsafe_cast", "unsafe_call_argument",
              "unsafe_void_return", "return_value_discarded", "shadowed_variable",
              "shadowed_variable_base_class", "unused_variable", "unused_parameter",
              "narrowing_conversion")
# Life Log RPG - 主控制器
# 重构后: 只负责启动序列 + 主循环 + 模块串接
# 具体逻辑在各模块: loader / world / player / transport / npc / ui / playback
#
# 数据流: JSON -> LogLoader -> modules -> UI
# 模块间通信: signal + 共享引用 (no global state)

const CONFIG_PATH := "res://config.json"
const DEFAULT_LOG_PATH := "res://saved_logs/log_001.json"

# 配置
var config: Dictionary = {}
var log_path: String = DEFAULT_LOG_PATH

# 模块
var loader: LogLoader
var world: WorldBuilder
var player: Player
var ui_sys: UISystem
var transport: TransportSystem
var npc_sys: NpcSystem
var playback: PlaybackController
var camera: Camera2D

# 数据 (来自 loader)
var waypoints: Array = []
var dialogs: Array = []


func _ready() -> void:
    _load_config()
    _resolve_log_path()
    _load_log()
    _build_modules()
    _wire_signals()
    _start()
    print("[LifeLogRPG] Ready. Log: ", log_path)


# =====================================================================
#  启动
# =====================================================================

func _load_config() -> void:
    if not FileAccess.file_exists(CONFIG_PATH):
        push_warning("config.json not found, using defaults")
        config = {"bake": {"tile_size_px": 16}, "playback": {"default_speed": 1.0, "min_speed": 0.25, "max_speed": 8.0}}
        return
    var f := FileAccess.open(CONFIG_PATH, FileAccess.READ)
    var json := JSON.new()
    if json.parse(f.get_as_text()) != OK:
        config = {"bake": {"tile_size_px": 16}, "playback": {"default_speed": 1.0, "min_speed": 0.25, "max_speed": 8.0}}
    else:
        config = json.data
    f.close()


func _resolve_log_path() -> void:
    for arg in OS.get_cmdline_args():
        if arg.begins_with("--log="):
            log_path = arg.substr(6)
            return
    var env_log := OS.get_environment("LIFELOG_JSON")
    if env_log != "":
        log_path = env_log


func _load_log() -> void:
    loader = LogLoader.new()
    if loader.load(log_path).is_empty():
        push_warning("log 加载失败, 使用空数据")
    waypoints = loader.get_waypoints()
    dialogs = loader.get_dialogs()


func _build_modules() -> void:
    var tile_size: int = loader.get_tile_size()

    # 地图
    world = WorldBuilder.new()
    world.name = "World"
    add_child(world)
    world.build(loader)

    # 玩家
    player = Player.new()
    player.name = "Player"
    world.add_child(player)
    player.build(tile_size)
    if waypoints.size() > 0:
        var p0: Dictionary = waypoints[0]
        player.position = Vector2(int(p0.get("x", 0)) * tile_size + tile_size / 2.0,
                                  int(p0.get("y", 0)) * tile_size + tile_size / 2.0)

    # 相机
    camera = Camera2D.new()
    camera.enabled = true
    camera.zoom = Vector2(2, 2)
    camera.position_smoothing_enabled = true
    camera.position_smoothing_speed = 5.0
    add_child(camera)
    if player:
        camera.position = player.position

    # UI (创建 ui_layer 后才能给 TransportSystem 用)
    ui_sys = UISystem.new()
    add_child(ui_sys)
    ui_sys.setup(self)
    ui_sys.progress_bar.max_value = max(loader.get_total_duration(), 1.0)

    # Transport (需要 ui_layer 放 overlay)
    transport = TransportSystem.new()
    add_child(transport)
    transport.setup(ui_sys.ui_layer, player)
    if waypoints.size() > 0:
        transport.sync_current(String(waypoints[0].get("transport", "walking")))

    # NPC
    npc_sys = NpcSystem.new()
    add_child(npc_sys)
    npc_sys.setup(world.npc_layer, tile_size)

    # 播放控制
    playback = PlaybackController.new()
    add_child(playback)
    var pb_cfg: Dictionary = config.get("playback", {})
    playback.setup(
        loader.get_total_duration(),
        float(pb_cfg.get("min_speed", 0.25)),
        float(pb_cfg.get("max_speed", 8.0)),
        float(pb_cfg.get("default_speed", 1.0)),
    )


func _wire_signals() -> void:
    playback.time_changed.connect(_on_time_changed)


func _start() -> void:
    playback.start()
    var meta := loader.get_log_meta()
    ui_sys.update_status(meta.get("title", "Log"), meta.get("mood", "calm"))


# =====================================================================
#  主循环
# =====================================================================

func _process(delta: float) -> void:
    if playback == null:
        return
    var was_in_transition := transport.is_in_transition() if transport else false
    if not was_in_transition:
        playback.update(delta)
    _update_player_position()
    _update_camera()
    _update_npc()
    if playback.is_finished():
        ui_sys.speed_label.text = "Playback finished. Press R to restart."


func _on_time_changed(_t: float) -> void:
    ui_sys.update_progress(playback.current_time, playback.total_duration)
    ui_sys.update_speed(playback.is_playing, playback.play_speed, playback.current_time, playback.total_duration)
    _check_transport_change()
    _update_dialog()


# =====================================================================
#  位置/朝向/相机
# =====================================================================

func _update_player_position() -> void:
    if not player or waypoints.size() < 2:
        return
    var tile_size: int = loader.get_tile_size()
    var t: float = playback.current_time
    var i: int = _find_segment(t)
    if i >= waypoints.size() - 1:
        i = waypoints.size() - 2
    var a: Dictionary = waypoints[i]
    var b: Dictionary = waypoints[i + 1]
    var ta: float = float(a.get("t", 0))
    var tb: float = float(b.get("t", ta + 1.0))
    var seg: float = max(tb - ta, 0.001)
    var ratio: float = clamp((t - ta) / seg, 0.0, 1.0)
    var ax: float = int(a.get("x", 0)) * tile_size + tile_size / 2.0
    var ay: float = int(a.get("y", 0)) * tile_size + tile_size / 2.0
    var bx: float = int(b.get("x", 0)) * tile_size + tile_size / 2.0
    var by: float = int(b.get("y", 0)) * tile_size + tile_size / 2.0
    player.position = Vector2(lerp(ax, bx, ratio), lerp(ay, by, ratio))
    _update_facing_direction(i, a, b)


func _find_segment(t: float) -> int:
    for k in range(waypoints.size() - 1):
        if t >= float(waypoints[k].get("t", 0)) and t <= float(waypoints[k + 1].get("t", 0)):
            return k
    return waypoints.size() - 2


func _update_facing_direction(i: int, a: Dictionary, b: Dictionary) -> void:
    var eye: Node = player.get_eye_node() if player else null
    if not eye:
        return
    var s: float = float(loader.get_tile_size())
    var ax: float = int(a.get("x", 0))
    var ay: float = int(a.get("y", 0))
    var bx: float = int(b.get("x", 0))
    var by: float = int(b.get("y", 0))
    var dir := Vector2(bx - ax, by - ay)
    if dir.length() < 0.01:
        return
    if abs(dir.x) > abs(dir.y):
        eye.position = Vector2(s * 0.05 if dir.x > 0 else -s * 0.15, -s * 0.6)
    else:
        eye.position = Vector2(0, -s * 0.65 if dir.y < 0 else -s * 0.55)


func _update_camera() -> void:
    if camera and player:
        camera.position = player.position


func _update_npc() -> void:
    if npc_sys and player:
        npc_sys.update(playback.current_time, dialogs, player.global_position)


# =====================================================================
#  换乘 / 对话
# =====================================================================

func _check_transport_change() -> void:
    if transport.is_in_transition() or waypoints.is_empty():
        return
    var new_transport := _get_transport_at(playback.current_time)
    if new_transport != transport.get_current() and new_transport != "":
        transport.request_switch(transport.get_current(), new_transport)


func _get_transport_at(t: float) -> String:
    if waypoints.is_empty():
        return ""
    var last: Dictionary = waypoints[0]
    for wp in waypoints:
        if float(wp.get("t", 0)) <= t:
            last = wp
        else:
            break
    return String(last.get("transport", "walking"))


var _current_dialog_idx: int = -1

func _update_dialog() -> void:
    if dialogs.is_empty():
        return
    var idx: int = -1
    for k in range(dialogs.size()):
        if playback.current_time >= float(dialogs[k].get("t", 0)):
            idx = k
    if idx == _current_dialog_idx:
        return
    _current_dialog_idx = idx
    if idx >= 0 and idx < dialogs.size():
        var d: Dictionary = dialogs[idx]
        ui_sys.update_dialog(String(d.get("speaker", "?")), String(d.get("text", "")))
    else:
        ui_sys.reset_dialog()


# =====================================================================
#  输入
# =====================================================================

func _unhandled_input(event: InputEvent) -> void:
    if event.is_action_pressed("play_pause"):
        playback.toggle()
    elif event.is_action_pressed("play_speed_up"):
        playback.bump_speed_up()
    elif event.is_action_pressed("play_speed_down"):
        playback.bump_speed_down()
    elif event is InputEventKey and event.pressed and event.keycode == KEY_R:
        playback.reset()
        _current_dialog_idx = -1
    elif event is InputEventMouseButton and event.pressed and ui_sys.progress_bar:
        var bar: ProgressBar = ui_sys.progress_bar
        if bar.get_global_rect().has_point(event.position):
            var ratio: float = (event.position.x - bar.global_position.x) / max(bar.size.x, 1.0)
            playback.seek_to(clamp(ratio, 0.0, 1.0) * playback.total_duration)
            _current_dialog_idx = -1
