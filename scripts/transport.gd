extends Node
class_name TransportSystem
# TransportSystem - 换乘动画 (黑屏淡入淡出 + sprite 切换 + 文字提示)
#
# 用法:
#   var ts = TransportSystem.new()
#   ts.setup(ui_layer, player)
#   ts.request_switch("walking", "transit")   # 触发切换
#
# 状态:
#   is_in_transition() -> bool
#   get_current() -> String

const TRANSPORT_ZH: Dictionary = {
    "walking": "走路", "driving": "开车", "transit": "坐地铁", "bicycling": "骑车",
}

var player
var overlay: ColorRect
var label: Label
var _current: String = "walking"
var _in_transition: bool = false
var _transition: Tween


func setup(p_ui_layer, p_player) -> void:
    """p_ui_layer: CanvasLayer, p_player: Player — 类型省略以避免 GDScript 静态推断问题"""
    player = p_player
    overlay = ColorRect.new()
    overlay.color = Color(0, 0, 0, 0)
    overlay.size = Vector2(1280, 720)
    overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
    overlay.z_index = 100
    p_ui_layer.add_child(overlay)
    label = Label.new()
    label.text = ""
    label.add_theme_color_override("font_color", Color.WHITE)
    label.add_theme_color_override("font_outline_color", Color.BLACK)
    label.add_theme_constant_override("outline_size", 4)
    label.add_theme_font_size_override("font_size", 32)
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    label.position = Vector2(0, 320)
    label.size = Vector2(1280, 80)
    label.z_index = 101
    p_ui_layer.add_child(label)


func is_in_transition() -> bool:
    return _in_transition


func get_current() -> String:
    return _current


func request_switch(from: String, to: String) -> void:
    """触发一次换乘动画: 0.3s 淡出 -> 切 sprite + 显示提示 -> 0.8s 停留 -> 0.3s 淡入"""
    if _in_transition or from == to:
        return
    _in_transition = true
    var tween := create_tween()
    _transition = tween
    tween.set_parallel(false)
    # 淡出
    tween.tween_property(overlay, "color:a", 0.85, 0.3)
    # 切 sprite + 显示文字
    tween.tween_callback(func():
        if player:
            player.switch_to(to)
        _current = to
        label.text = "从「%s」切换到「%s」" % [String(TRANSPORT_ZH.get(from, from)), String(TRANSPORT_ZH.get(to, to))]
    )
    # 停留
    tween.tween_interval(0.8)
    # 淡入
    tween.tween_property(overlay, "color:a", 0.0, 0.3)
    tween.tween_callback(func():
        label.text = ""
        _in_transition = false
    )


func sync_current(transport: String) -> void:
    """初始化或跳转时直接同步交通方式。"""
    if _in_transition:
        _transition.kill()
        overlay.color.a = 0.0
        label.text = ""
        _in_transition = false
    if player:
        player.switch_to(transport)
    _current = transport
