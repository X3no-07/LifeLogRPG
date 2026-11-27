extends Node
class_name UISystem
# UISystem - 所有 UI 控件 (进度条, 速度, 状态, 对话框)
#
# 公开节点 (其他模块可读):
#   progress_bar: ProgressBar
#   speed_label: Label
#   status_label: Label
#   dialog_label: Label
#
# 用法:
#   var ui = UISystem.new()
#   ui.setup(self)            # add_child 到 self (Main)
#   ui.update_progress(t, total)
#   ui.update_speed(is_playing, speed, t, total)
#   ui.update_status(title, mood)
#   ui.update_dialog(speaker, text)
#   ui.reset_dialog()

var ui_layer: CanvasLayer
var progress_bar: ProgressBar
var speed_label: Label
var status_label: Label
var dialog_label: Label
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

    progress_bar = ProgressBar.new()
    progress_bar.min_value = 0.0
    progress_bar.max_value = 1.0
    progress_bar.value = 0.0
    progress_bar.custom_minimum_size = Vector2(360, 16)
    progress_bar.show_percentage = false
    progress_bar.mouse_filter = Control.MOUSE_FILTER_STOP
    vbox.add_child(progress_bar)

    speed_label = Label.new()
    speed_label.text = "Speed: 1.0x  (SPACE pause, UP/DOWN speed)"
    vbox.add_child(speed_label)

    dialog_label = Label.new()
    dialog_label.text = ""
    dialog_label.add_theme_color_override("font_color", Color.WHITE)
    dialog_label.add_theme_color_override("font_outline_color", Color.BLACK)
    dialog_label.add_theme_constant_override("outline_size", 4)
    dialog_label.position = Vector2(16, 640)
    dialog_label.add_theme_font_size_override("font_size", 18)
    ui_layer.add_child(dialog_label)
    _setup_destination_panel()


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


func update_progress(current_time: float, total_duration: float) -> void:
    if progress_bar:
        progress_bar.max_value = max(total_duration, 1.0)
        progress_bar.value = current_time


func update_speed(is_playing: bool, speed: float, current_time: float, total_duration: float) -> void:
    if speed_label:
        var state := "▶" if is_playing else "⏸"
        speed_label.text = "%s  Speed: %.2fx  Time: %.1f / %.1fs" % [state, speed, current_time, total_duration]


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
