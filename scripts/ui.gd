extends Node
class_name UISystem

signal play_pause_requested
signal replay_requested
signal scrub_started
signal seek_requested(time: float)
signal scrub_ended

var ui_layer: CanvasLayer
var status_label: Label
var dialog_label: Label
var timeline: HSlider
var _play_pause: Button
var _replay: Button
var _time_label: Label
var _speed_label: Label
var _destination_panel: PanelContainer
var _destination_status: Label
var _destination_name: Label
var _destination_detail: Label


func setup(parent: Node) -> void:
    ui_layer = CanvasLayer.new()
    parent.add_child(ui_layer)

    var panel := PanelContainer.new()
    panel.position = Vector2(16, 16)
    ui_layer.add_child(panel)
    var vbox := VBoxContainer.new()
    panel.add_child(vbox)

    status_label = Label.new()
    status_label.text = "Life Log RPG"
    vbox.add_child(status_label)

    dialog_label = Label.new()
    dialog_label.text = ""
    dialog_label.add_theme_color_override("font_color", Color.WHITE)
    dialog_label.add_theme_color_override("font_outline_color", Color.BLACK)
    dialog_label.add_theme_constant_override("outline_size", 4)
    dialog_label.add_theme_font_size_override("font_size", 18)
    ui_layer.add_child(dialog_label)
    dialog_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
    dialog_label.offset_left = 16
    dialog_label.offset_top = -124
    _setup_playback_controls()
    _setup_destination_panel()


func _setup_playback_controls() -> void:
    var panel := PanelContainer.new()
    panel.name = "PlaybackControls"
    panel.z_index = 102
    ui_layer.add_child(panel)
    panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
    panel.offset_left = -380
    panel.offset_right = 380
    panel.offset_top = -85
    panel.offset_bottom = -34
    var style := StyleBoxFlat.new()
    style.bg_color = Color("#15262e")
    style.border_color = Color("#36515b")
    style.set_border_width_all(1)
    style.set_corner_radius_all(6)
    style.content_margin_left = 12
    style.content_margin_right = 12
    style.content_margin_top = 6
    style.content_margin_bottom = 6
    panel.add_theme_stylebox_override("panel", style)

    var controls := HBoxContainer.new()
    controls.add_theme_constant_override("separation", 12)
    panel.add_child(controls)
    _play_pause = Button.new()
    _play_pause.name = "PlayPause"
    _play_pause.text = "播放"
    _play_pause.tooltip_text = "播放或暂停（空格）"
    _play_pause.custom_minimum_size = Vector2(58, 32)
    _play_pause.pressed.connect(func() -> void: play_pause_requested.emit())
    controls.add_child(_play_pause)

    _replay = Button.new()
    _replay.name = "Replay"
    _replay.text = "重播"
    _replay.tooltip_text = "从开头播放（R）"
    _replay.custom_minimum_size = Vector2(58, 32)
    _replay.pressed.connect(func() -> void: replay_requested.emit())
    controls.add_child(_replay)

    timeline = HSlider.new()
    timeline.name = "Timeline"
    timeline.tooltip_text = "点击或拖动以跳转回放"
    timeline.custom_minimum_size.x = 180
    timeline.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    timeline.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    timeline.step = 0.01
    timeline.scrollable = false
    timeline.drag_started.connect(func() -> void: scrub_started.emit())
    timeline.value_changed.connect(func(time: float) -> void: seek_requested.emit(time))
    timeline.drag_ended.connect(func(_changed: bool) -> void: scrub_ended.emit())
    controls.add_child(timeline)

    _time_label = Label.new()
    _time_label.custom_minimum_size.x = 144
    _time_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    controls.add_child(_time_label)
    _speed_label = Label.new()
    _speed_label.custom_minimum_size.x = 52
    _speed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    _speed_label.tooltip_text = "↑ 加速 / ↓ 减速"
    _speed_label.mouse_filter = Control.MOUSE_FILTER_STOP
    controls.add_child(_speed_label)
    update_playback(0.0, 0.0, false, 1.0)


func show_map_attribution() -> void:
    var credit := Label.new()
    credit.text = "© OpenStreetMap contributors"
    credit.mouse_filter = Control.MOUSE_FILTER_IGNORE
    credit.add_theme_font_size_override("font_size", 12)
    credit.add_theme_color_override("font_outline_color", Color("15232b"))
    credit.add_theme_constant_override("outline_size", 4)
    credit.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    ui_layer.add_child(credit)
    credit.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
    credit.offset_left = -235
    credit.offset_right = -16
    credit.offset_top = -28
    credit.offset_bottom = -9


func add_return_button(go_back: Callable) -> void:
    var button := Button.new()
    button.text = "返回首页  Esc"
    button.focus_mode = Control.FOCUS_NONE
    button.pressed.connect(go_back)
    ui_layer.add_child(button)
    button.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
    button.offset_left = -66
    button.offset_right = 66
    button.offset_top = 16
    button.offset_bottom = 48


func _setup_destination_panel() -> void:
    _destination_panel = PanelContainer.new()
    _destination_panel.name = "DestinationCard"
    _destination_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
    ui_layer.add_child(_destination_panel)
    _destination_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
    _destination_panel.offset_left = -328
    _destination_panel.offset_right = -16
    _destination_panel.offset_top = 16
    var style := StyleBoxFlat.new()
    style.bg_color = Color(0.08, 0.12, 0.16, 0.95)
    style.border_color = Color("5ddabe")
    style.border_width_left = 3
    style.content_margin_left = 16
    style.content_margin_right = 16
    style.content_margin_top = 12
    style.content_margin_bottom = 12
    _destination_panel.add_theme_stylebox_override("panel", style)

    var content := VBoxContainer.new()
    content.mouse_filter = Control.MOUSE_FILTER_IGNORE
    content.add_theme_constant_override("separation", 4)
    _destination_panel.add_child(content)

    _destination_status = Label.new()
    _destination_status.add_theme_color_override("font_color", Color("88edda"))
    content.add_child(_destination_status)

    _destination_name = Label.new()
    _destination_name.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    _destination_name.add_theme_font_size_override("font_size", 22)
    content.add_child(_destination_name)

    _destination_detail = Label.new()
    _destination_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    _destination_detail.add_theme_color_override("font_color", Color("c0cdd1"))
    content.add_child(_destination_detail)
    _destination_panel.hide()


func update_destination(stop: Dictionary, arrived: bool, is_final: bool) -> void:
    var name := String(stop.get("name", "")).strip_edges()
    var category := String(stop.get("category", "")).strip_edges()
    var detail := PackedStringArray()
    if not name.is_empty() and not category.is_empty() and name != category:
        detail.append(category)
    if bool(stop.get("entrance", false)):
        detail.append("地图标注入口")
    _destination_status.text = "已到达" if arrived else "下一站"
    _destination_name.text = name if not name.is_empty() else category
    if _destination_name.text.is_empty():
        _destination_name.text = "路线终点" if is_final else "途经点"
    _destination_detail.text = " · ".join(detail)
    _destination_detail.visible = not detail.is_empty()
    _destination_panel.show()


func update_playback(current_time: float, total_duration: float, is_playing: bool, speed: float) -> void:
    if timeline.max_value != total_duration:
        timeline.max_value = total_duration
    timeline.set_value_no_signal(current_time)
    timeline.editable = total_duration > 0.0
    _play_pause.disabled = total_duration <= 0.0 or current_time >= total_duration
    _play_pause.text = "暂停" if is_playing else "播放"
    _replay.disabled = total_duration <= 0.0
    _time_label.text = "%s / %s" % [_timestamp(current_time), _timestamp(total_duration)]
    _speed_label.text = "×%.2f" % speed


func _timestamp(time: float) -> String:
    var tenths := int(maxf(0.0, time) * 10.0)
    return "%d:%02d.%d" % [tenths / 600, (tenths / 10) % 60, tenths % 10]


func update_status(title: String, mood: String) -> void:
    if status_label:
        status_label.text = "%s  |  %s" % [title, mood]


func update_dialog(speaker: String, text: String) -> void:
    if dialog_label:
        if text == "":
            dialog_label.text = ""
        else:
            dialog_label.text = "[%s] %s" % [speaker, text]


func reset_dialog() -> void:
    if dialog_label:
        dialog_label.text = ""
