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
