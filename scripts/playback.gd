extends Node
class_name PlaybackController
# PlaybackController - 播放控制: 时间推进, 暂停, 倍速, 跳转
#
# 公开信号:
#   time_changed(current_time: float)
#
# 公开 API:
#   start() / pause() / toggle()
#   set_speed(speed: float)
#   bump_speed_up() / bump_speed_down()
#   seek_to(t: float)   # 跳转
#   reset()             # 回到 0
#   update(delta)       # 主循环调
#
# 输入 (在 main.gd 转发):
#   handle_input(event)

signal time_changed(current_time: float)

var is_playing: bool = false
var play_speed: float = 1.0
var current_time: float = 0.0
var total_duration: float = 0.0
var min_speed: float = 0.25
var max_speed: float = 8.0
var default_speed: float = 1.0


func setup(p_total: float, p_min_speed: float, p_max_speed: float, p_default: float) -> void:
    total_duration = p_total
    min_speed = p_min_speed
    max_speed = p_max_speed
    default_speed = p_default
    play_speed = default_speed
    current_time = 0.0


func start() -> void:
    is_playing = true


func pause() -> void:
    is_playing = false


func toggle() -> void:
    if is_playing and current_time >= total_duration:
        reset()
    is_playing = not is_playing


func set_speed(s: float) -> void:
    play_speed = clamp(s, min_speed, max_speed)


func bump_speed_up() -> void:
    set_speed(play_speed * 2.0)


func bump_speed_down() -> void:
    set_speed(play_speed * 0.5)


func seek_to(t: float) -> void:
    current_time = clamp(t, 0.0, total_duration)


func reset() -> void:
    current_time = 0.0
    is_playing = true


func update(delta: float) -> void:
    if not is_playing:
        return
    current_time += delta * play_speed
    if current_time >= total_duration:
        current_time = total_duration
        is_playing = false
    time_changed.emit(current_time)


func is_finished() -> bool:
    return current_time >= total_duration
