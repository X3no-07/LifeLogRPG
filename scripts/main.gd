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
#
# 注: 用 preload 代替 class_name 全局注册 (Godot headless 模式不写 class cache,
#     单独 --import 不一定触发, preload 是稳定方案)

const LogLoaderClass = preload("res://scripts/loader.gd")
const WorldBuilderClass = preload("res://scripts/world.gd")
const PlayerClass = preload("res://scripts/player.gd")
const UISystemClass = preload("res://scripts/ui.gd")
const TransportSystemClass = preload("res://scripts/transport.gd")
const NpcSystemClass = preload("res://scripts/npc.gd")
const PlaybackControllerClass = preload("res://scripts/playback.gd")
const BakeLoadingSceneClass = preload("res://scripts/loading.gd")
const AudioSystemClass = preload("res://scripts/audio.gd")
const WeatherSystemClass = preload("res://scripts/weather.gd")
const AvatarBuilderClass = preload("res://scripts/avatar_builder.gd")

const CONFIG_PATH := "res://config.json"
const DEFAULT_LOG_PATH := "res://saved_logs/log_001.json"

signal return_requested

# 配置
var config: Dictionary = {}
var log_path: String = DEFAULT_LOG_PATH
var launcher_managed := false

# 模块 (preload 拿到 Script, 不写类型注解因为 GDScript 静态推断有限)
var loader
var world
var player
var ui_sys
var transport
var npc_sys
var playback
var audio
var weather
var camera: Camera2D

# 数据 (来自 loader)
var waypoints: Array = []
var dialogs: Array = []
var stops: Array[Dictionary] = []
var _displayed_stop: int = -1
var _displayed_arrived: bool = false
var _started := false
var _resume_after_scrub := false


func _ready() -> void:
    _load_config()
    _resolve_log_path()
    _load_log()
    _build_modules()
    _wire_signals()
    # 启动序列: 捏脸 → loading → 播放
    _play_avatar_builder_then_loading()
    print("[LifeLogRPG] Ready. Log: ", log_path)


func _play_avatar_builder_then_loading() -> void:
    var ab = AvatarBuilderClass.new()
    add_child(ab)
    # 如果有已保存的 avatar, 直接用; 否则显示捏脸 UI
    var saved = AvatarBuilderClass.load_avatar()
    # 检查是否需要展示捏脸: 如果有 --force-avatar 命令行参数 或 saved 是空
    var force := false
    for arg in OS.get_cmdline_args():
        if arg == "--force-avatar" or arg == "--avatar":
            force = true
            break
    if saved.is_empty() or force:
        ab.confirmed.connect(_on_avatar_confirmed)
        ab.show_builder({})
    else:
        # 已有 avatar, 跳过捏脸直接 loading
        _apply_avatar_to_player(saved)
        _play_loading()


func _on_avatar_confirmed(avatar: Dictionary) -> void:
    _apply_avatar_to_player(avatar)
    _play_loading()


func _apply_avatar_to_player(avatar: Dictionary) -> void:
    if player and player.has_method("apply_avatar"):
        player.apply_avatar(avatar)


func _play_loading() -> void:
    var loading = BakeLoadingSceneClass.new()
    add_child(loading)
    loading.finished.connect(_on_loading_finished)
    loading.play()


func _on_loading_finished() -> void:
    _start()
    if audio:
        audio.play_music()


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
    if launcher_managed:
        return
    for arg in OS.get_cmdline_args():
        if arg.begins_with("--log="):
            log_path = arg.substr(6)
            return
    var env_log := OS.get_environment("LIFELOG_JSON")
    if env_log != "":
        log_path = env_log


func _load_log() -> void:
    loader = LogLoaderClass.new()
    if loader.load(log_path).is_empty():
        push_warning("log 加载失败, 使用空数据")
    waypoints = loader.get_waypoints()
    dialogs = loader.get_dialogs()
    stops = loader.get_stops()


func _build_modules() -> void:
    var tile_size: int = loader.get_tile_size()

    # 地图
    world = WorldBuilderClass.new()
    world.name = "World"
    add_child(world)
    world.build(loader)

    # 玩家
    player = PlayerClass.new()
    player.name = "Player"
    world.add_child(player)
    player.build(tile_size)
    if waypoints.size() > 0:
        var p0: Dictionary = waypoints[0]
        player.position = (Vector2(float(p0.get("x", 0)), float(p0.get("y", 0))) + Vector2(0.5, 0.5)) * tile_size

    # 相机: 直接跟随人物, 不用位置平滑
    # 平滑会让相机滞后人物 (滞后量 = 速度 / 平滑速度), 速度一变、拐弯、
    # 换乘停顿时滞后量跟着变, 人物就在画面里来回晃 (抖动); 直接跟随则
    # 人物永远在画面中心、地图在下面匀速走, 不晃。拐弯处方向瞬间变,
    # 一帧的事, 不是抖动。
    camera = Camera2D.new()
    camera.enabled = true
    camera.zoom = Vector2(2, 2)
    add_child(camera)
    if player:
        camera.position = _clamp_camera_position(player.position)

    # UI (创建 ui_layer 后才能给 TransportSystem 用)
    ui_sys = UISystemClass.new()
    add_child(ui_sys)
    ui_sys.setup(self)
    if launcher_managed:
        ui_sys.add_return_button(func(): return_requested.emit())

    # Transport (需要 ui_layer 放 overlay)
    transport = TransportSystemClass.new()
    add_child(transport)
    transport.setup(ui_sys.ui_layer, player)
    if waypoints.size() > 0:
        transport.sync_current(String(waypoints[0].get("transport", "walking")))

    # NPC
    npc_sys = NpcSystemClass.new()
    add_child(npc_sys)
    npc_sys.setup(world.npc_layer, tile_size)

    # 播放控制
    playback = PlaybackControllerClass.new()
    add_child(playback)
    var pb_cfg: Dictionary = config.get("playback", {})
    playback.setup(
        loader.get_total_duration(),
        float(pb_cfg.get("min_speed", 0.25)),
        float(pb_cfg.get("max_speed", 8.0)),
        float(pb_cfg.get("default_speed", 1.0)),
    )

    # 8-Bit BGM (程序化生成, 无需外部素材)
    audio = AudioSystemClass.new()
    add_child(audio)
    audio.setup()

    # 天气粒子 (根据 meta.weather, 必须 add 到 world 跟随相机)
    var meta: Dictionary = loader.get_log_meta()
    if "[OSM]" in String(meta.get("raw_text", "")):
        ui_sys.show_map_attribution()
    weather = WeatherSystemClass.new()
    weather.name = "Weather"
    world.add_child(weather)
    weather.setup(loader.get_grid_width(), loader.get_grid_height(),
                  String(meta.get("weather", "unknown")))


func _wire_signals() -> void:
    playback.time_changed.connect(_on_time_changed)
    ui_sys.play_pause_requested.connect(_toggle_play_pause)
    ui_sys.replay_requested.connect(_replay)
    ui_sys.scrub_started.connect(_begin_scrub)
    ui_sys.seek_requested.connect(_seek)
    ui_sys.scrub_ended.connect(_end_scrub)


func _start() -> void:
    _started = true
    if playback.total_duration > 0.0:
        playback.start()
    ui_sys.update_status(loader.get_log_meta().get("title", "Log"),
                         loader.get_log_meta().get("mood", "calm"))
    _refresh_playback_ui()


# =====================================================================
#  主循环
# =====================================================================

func _process(delta: float) -> void:
    if playback == null:
        return
    var was_in_transition: bool = transport.is_in_transition() if transport else false
    if not was_in_transition:
        playback.update(delta)
    _update_player_position()
    _update_camera()
    _update_npc()


func _on_time_changed(_t: float) -> void:
    _refresh_playback_ui()
    _check_transport_change()


func _refresh_playback_ui() -> void:
    ui_sys.update_playback(playback.current_time, playback.total_duration, playback.is_playing, playback.play_speed)
    _update_dialog()
    _update_destination()


func _update_destination() -> void:
    if stops.is_empty():
        return
    var now: float = playback.current_time
    var index: int = stops.size() - 1
    var arrived := true
    for i in range(stops.size()):
        if now < float(stops[i]["t"]):
            arrived = i > 0 and now - float(stops[i - 1]["t"]) < 2.0
            index = i - 1 if arrived else i
            break
    if index == _displayed_stop and arrived == _displayed_arrived:
        return
    _displayed_stop = index
    _displayed_arrived = arrived
    world.show_stop(stops[index], arrived)
    ui_sys.update_destination(stops[index], arrived, index == stops.size() - 1)


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
    var ax: float = float(a.get("x", 0)) * tile_size + tile_size / 2.0
    var ay: float = float(a.get("y", 0)) * tile_size + tile_size / 2.0
    var bx: float = float(b.get("x", 0)) * tile_size + tile_size / 2.0
    var by: float = float(b.get("y", 0)) * tile_size + tile_size / 2.0
    player.position = Vector2(lerp(ax, bx, ratio), lerp(ay, by, ratio))
    var heading := Vector2(bx - ax, by - ay)
    var moving: bool = (playback.is_playing and not transport.is_in_transition()
        and tb > ta and not heading.is_zero_approx())
    if moving and player.get_current() == "walking":
        # Densified routes often alternate short horizontal and vertical steps.
        var behind: Dictionary = waypoints[_find_segment(maxf(t - 0.12, 0.0))]
        var ahead: Dictionary = waypoints[_find_segment(minf(t + 0.12, playback.total_duration)) + 1]
        var travel := Vector2(float(ahead["x"]) - float(behind["x"]), float(ahead["y"]) - float(behind["y"]))
        if not travel.is_zero_approx():
            heading = travel
    player.set_walk_state(heading, moving)


func _find_segment(t: float) -> int:
    var first := 0
    var last := waypoints.size() - 2
    while first < last:
        var middle := (first + last) / 2
        if t > float(waypoints[middle + 1].get("t", 0)):
            first = middle + 1
        else:
            last = middle
    return first


func _update_camera() -> void:
    if camera and player:
        var position_on_map := _clamp_camera_position(player.position)
        var screen_scale := get_viewport().get_stretch_transform().get_scale() * camera.zoom
        camera.position = (position_on_map * screen_scale).round() / screen_scale
        camera.force_update_scroll()


func _clamp_camera_position(pos: Vector2) -> Vector2:
    # 把相机中心夹到地图边界内: 视口不能伸出地图外, 否则露出地图外的深色底。
    # 地图原点在 (0,0), 尺寸 = 网格 x tile_size; 可见世界尺寸 = 视口 / zoom。
    # 地图比视口小 (老 80x60 小 bake) 时居中, 不夹死。
    if camera == null or loader == null:
        return pos
    var tile_size: int = loader.get_tile_size()
    var map_px := Vector2(
        loader.get_grid_width() * tile_size,
        loader.get_grid_height() * tile_size)
    var view_world: Vector2 = get_viewport().get_visible_rect().size / camera.zoom
    var half: Vector2 = view_world * 0.5
    var cx: float
    var cy: float
    if map_px.x <= view_world.x:
        cx = map_px.x * 0.5
    else:
        cx = clamp(pos.x, half.x, map_px.x - half.x)
    if map_px.y <= view_world.y:
        cy = map_px.y * 0.5
    else:
        cy = clamp(pos.y, half.y, map_px.y - half.y)
    return Vector2(cx, cy)


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
    if launcher_managed and event.is_action_pressed("ui_cancel"):
        return_requested.emit()
        return
    if not _started:
        return
    if event.is_action_pressed("play_pause"):
        _toggle_play_pause()
    elif event.is_action_pressed("play_speed_up"):
        playback.bump_speed_up()
        _refresh_playback_ui()
    elif event.is_action_pressed("play_speed_down"):
        playback.bump_speed_down()
        _refresh_playback_ui()
    elif event is InputEventKey and event.pressed and event.keycode == KEY_R:
        _replay()


func _toggle_play_pause() -> void:
    if playback.total_duration <= 0.0:
        return
    if playback.is_finished():
        _replay()
        return
    playback.toggle()
    _refresh_playback_ui()


func _replay() -> void:
    if playback.total_duration <= 0.0:
        return
    playback.reset()
    _seek(0.0)
    audio.play_music()


func _begin_scrub() -> void:
    _resume_after_scrub = playback.is_playing
    playback.pause()
    _refresh_playback_ui()


func _end_scrub() -> void:
    if _resume_after_scrub and not playback.is_finished():
        playback.start()
    _resume_after_scrub = false
    _refresh_playback_ui()


func _seek(time: float) -> void:
    playback.seek_to(time)
    if playback.is_finished():
        playback.pause()
    var mode := _get_transport_at(playback.current_time)
    if not mode.is_empty():
        transport.sync_current(mode)
    _refresh_playback_ui()
    _update_player_position()
    _update_camera()
    _update_npc()
