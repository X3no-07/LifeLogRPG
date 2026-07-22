extends Node
class_name AvatarBuilder
# AvatarBuilder - 像素捏脸/形象自定义
#
# 5 个图层, 共 72 种组合:
#   hair (3)  × skin (3)  × shirt (3) × pants (2) × accessory (2) = 108
#   实际用: 3*3*3*2*2 = 108
#
# 用法:
#   var ab = AvatarBuilder.new()
#   add_child(ab)
#   ab.confirmed.connect(_on_avatar_confirmed)
#   ab.show_builder(initial: Dictionary = {})
#
# 配置存到 res://saved_logs/avatar.json, 启动时自动读
# signal confirmed(avatar: Dictionary)  // {hair, skin, shirt, pants, accessory}

signal confirmed(avatar: Dictionary)

const AVATAR_PATH := "res://saved_logs/avatar.json"
const PREVIEW_SCALE := 4  # 预览放大倍数 (16px * 4 = 64px)

# 颜色配方 (每图层是一个 Color + 形状描述)
# shape = [[x, y, w, h], ...]  (相对 -8..8 中心, 单位 1px)
const OPTIONS := {
    "hair": [
        {"id": "spike", "name": "尖发", "color": Color8(50, 30, 20),
         "parts": [
            {"x": -5, "y": -10, "w": 10, "h": 3},  # 顶部
            {"x": -3, "y": -13, "w": 2, "h": 3},  # 左侧尖
            {"x": 1, "y": -13, "w": 2, "h": 3},   # 右侧尖
         ]},
        {"id": "bob", "name": "波波头", "color": Color8(120, 70, 30),
         "parts": [
            {"x": -5, "y": -10, "w": 10, "h": 4},
            {"x": -7, "y": -6, "w": 2, "h": 4},    # 左侧垂发
            {"x": 5, "y": -6, "w": 2, "h": 4},     # 右侧垂发
         ]},
        {"id": "bald", "name": "光头", "color": Color8(200, 150, 100),
         "parts": [
            {"x": -5, "y": -10, "w": 10, "h": 2},   # 光头高光
         ]},
    ],
    "skin": [
        {"id": "light", "name": "白皮肤", "color": Color8(245, 215, 175), "parts": []},
        {"id": "medium", "name": "黄皮肤", "color": Color8(230, 190, 140), "parts": []},
        {"id": "dark", "name": "深皮肤", "color": Color8(160, 110, 70), "parts": []},
    ],
    "shirt": [
        {"id": "red", "name": "红 T 恤", "color": Color8(220, 60, 60),
         "parts": [{"x": -5, "y": -2, "w": 10, "h": 5}]},
        {"id": "blue", "name": "蓝 T 恤", "color": Color8(60, 110, 200),
         "parts": [{"x": -5, "y": -2, "w": 10, "h": 5}]},
        {"id": "white", "name": "白衬衫", "color": Color8(245, 245, 245),
         "parts": [{"x": -5, "y": -2, "w": 10, "h": 5}]},
    ],
    "pants": [
        {"id": "blue", "name": "蓝裤", "color": Color8(50, 80, 150),
         "parts": [{"x": -5, "y": 3, "w": 10, "h": 5}]},
        {"id": "black", "name": "黑裤", "color": Color8(40, 40, 50),
         "parts": [{"x": -5, "y": 3, "w": 10, "h": 5}]},
    ],
    "accessory": [
        {"id": "none", "name": "无", "color": Color.WHITE, "parts": []},
        {"id": "glasses", "name": "眼镜", "color": Color8(30, 30, 30),
         "parts": [
            {"x": -4, "y": -6, "w": 3, "h": 2},
            {"x": 1, "y": -6, "w": 3, "h": 2},
            {"x": -1, "y": -5, "w": 2, "h": 1},  # 鼻梁
         ]},
    ],
}

var _current: Dictionary = {
    "hair": "spike", "skin": "medium", "shirt": "red", "pants": "blue", "accessory": "none"
}
var _layer_buttons: Dictionary = {}  # {"hair": [Button, ...], ...}
var _preview_node: Node2D
var _summary_label: Label


func show_builder(initial: Dictionary = {}) -> void:
    """显示捏脸 UI, initial 可覆盖默认值"""
    for k in initial:
        if _current.has(k):
            _current[k] = initial[k]
    _build_ui()


# =====================================================================
#  UI 构建
# =====================================================================

func _build_ui() -> void:
    var canvas := CanvasLayer.new()
    canvas.layer = 150
    add_child(canvas)

    # 背景
    var bg := ColorRect.new()
    bg.color = Color8(25, 30, 45)
    bg.size = Vector2(1280, 720)
    canvas.add_child(bg)

    # 标题
    var title := Label.new()
    title.text = "像素捏脸 - Avatar Builder"
    title.add_theme_color_override("font_color", Color8(255, 220, 100))
    title.add_theme_color_override("font_outline_color", Color8(50, 20, 0))
    title.add_theme_constant_override("outline_size", 3)
    title.add_theme_font_size_override("font_size", 32)
    title.position = Vector2(40, 30)
    canvas.add_child(title)

    # 副标题
    var sub := Label.new()
    sub.text = "选完后点 [开始游戏]"
    sub.add_theme_color_override("font_color", Color8(180, 180, 180))
    sub.add_theme_font_size_override("font_size", 16)
    sub.position = Vector2(40, 75)
    canvas.add_child(sub)

    # ---- 左侧预览 ----
    var preview_frame := Panel.new()
    preview_frame.position = Vector2(40, 130)
    preview_frame.size = Vector2(360, 480)
    canvas.add_child(preview_frame)
    var frame_label := Label.new()
    frame_label.text = "预览"
    frame_label.add_theme_font_size_override("font_size", 14)
    frame_label.position = Vector2(40, 110)
    canvas.add_child(frame_label)

    _preview_node = Node2D.new()
    _preview_node.position = Vector2(220, 370)  # preview frame 中心
    _preview_node.scale = Vector2(PREVIEW_SCALE, PREVIEW_SCALE)
    canvas.add_child(_preview_node)

    # 摘要 (当前组合)
    _summary_label = Label.new()
    _summary_label.add_theme_color_override("font_color", Color8(200, 200, 100))
    _summary_label.add_theme_font_size_override("font_size", 14)
    _summary_label.position = Vector2(40, 620)
    _summary_label.size = Vector2(360, 80)
    canvas.add_child(_summary_label)

    # ---- 右侧选项 ----
    var options_x := 440.0
    var options_y := 130.0
    var layer_names_zh := {
        "hair": "发型", "skin": "肤色", "shirt": "上衣",
        "pants": "裤子", "accessory": "配饰"
    }
    for layer_id in ["hair", "skin", "shirt", "pants", "accessory"]:
        # 图层名
        var layer_label := Label.new()
        layer_label.text = layer_names_zh[layer_id] + ":"
        layer_label.add_theme_color_override("font_color", Color8(180, 220, 255))
        layer_label.add_theme_font_size_override("font_size", 18)
        layer_label.position = Vector2(options_x, options_y)
        canvas.add_child(layer_label)
        options_y += 28

        # 当前选项
        var cur_label := Label.new()
        cur_label.name = "Current_%s" % layer_id
        cur_label.add_theme_color_override("font_color", Color8(255, 220, 100))
        cur_label.add_theme_font_size_override("font_size", 16)
        cur_label.position = Vector2(options_x + 80, options_y)
        canvas.add_child(cur_label)

        # 按钮组 (左/右)
        var btn_box := HBoxContainer.new()
        btn_box.position = Vector2(options_x, options_y + 30)
        canvas.add_child(btn_box)
        _layer_buttons[layer_id] = []
        for opt in OPTIONS[layer_id]:
            var btn := Button.new()
            btn.text = opt["name"]
            btn.toggle_mode = true
            btn.custom_minimum_size = Vector2(120, 36)
            btn_box.add_child(btn)
            _layer_buttons[layer_id].append(btn)
            btn.pressed.connect(_on_select.bind(layer_id, opt["id"]))
        options_y += 100

    # ---- 开始按钮 ----
    var start_btn := Button.new()
    start_btn.text = "▶ 开 始 游 戏"
    start_btn.add_theme_color_override("font_color", Color8(100, 255, 100))
    start_btn.add_theme_font_size_override("font_size", 24)
    start_btn.custom_minimum_size = Vector2(280, 60)
    start_btn.position = Vector2(720, 580)
    canvas.add_child(start_btn)
    start_btn.pressed.connect(_on_start_pressed)

    # 初始 refresh
    _refresh_preview()
    _refresh_summary()
    _refresh_button_states()


# =====================================================================
#  拼装 + 预览
# =====================================================================

func _refresh_preview() -> void:
    if not _preview_node:
        return
    for child in _preview_node.get_children():
        child.queue_free()
    # 顺序: pants -> body (skin) -> shirt -> hair -> accessory -> face
    _draw_layer("pants")
    _draw_layer("skin")
    _draw_layer("shirt")
    _draw_layer("hair")
    _draw_layer("accessory")
    # 脸 (小点, 不管 hair 都显示)
    var eyes := ColorRect.new()
    eyes.color = Color.BLACK
    eyes.size = Vector2(2, 2)
    eyes.position = Vector2(-3, -5)
    _preview_node.add_child(eyes)
    var eye2 := ColorRect.new()
    eye2.color = Color.BLACK
    eye2.size = Vector2(2, 2)
    eye2.position = Vector2(1, -5)
    _preview_node.add_child(eye2)


func _draw_layer(layer_id: String) -> void:
    var opt_id: String = _current[layer_id]
    var opt: Dictionary = _get_option(layer_id, opt_id)
    if opt == null:
        return
    for part in opt["parts"]:
        var rect := ColorRect.new()
        rect.color = opt["color"]
        rect.size = Vector2(part["w"], part["h"])
        rect.position = Vector2(part["x"] - 8, part["y"] - 8)  # 中心化
        rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
        _preview_node.add_child(rect)


func _refresh_summary() -> void:
    if not _summary_label:
        return
    var parts := []
    for layer_id in ["hair", "skin", "shirt", "pants", "accessory"]:
        var opt: Dictionary = _get_option(layer_id, _current[layer_id])
        if opt and opt["id"] != "none":
            parts.append(opt["name"])
    _summary_label.text = "我的角色: " + " / ".join(parts)


func _refresh_button_states() -> void:
    for layer_id in _layer_buttons:
        for btn in _layer_buttons[layer_id]:
            var matches: bool = btn.text == _get_option(layer_id, _current[layer_id]).get("name", "")
            btn.button_pressed = matches


# =====================================================================
#  事件
# =====================================================================

func _on_select(layer_id: String, opt_id: String) -> void:
    _current[layer_id] = opt_id
    _refresh_preview()
    _refresh_summary()
    _refresh_button_states()


func _on_start_pressed() -> void:
    _save_avatar(_current)
    confirmed.emit(_current)


# =====================================================================
#  工具
# =====================================================================

func _get_option(layer_id: String, opt_id: String) -> Dictionary:
    for opt in OPTIONS[layer_id]:
        if opt["id"] == opt_id:
            return opt
    return {}


func _save_avatar(avatar: Dictionary) -> void:
    var f := FileAccess.open(AVATAR_PATH, FileAccess.WRITE)
    if f == null:
        push_warning("AvatarBuilder: cannot save to " + AVATAR_PATH)
        return
    f.store_string(JSON.stringify(avatar, "  "))
    f.close()


# =====================================================================
#  静态方法: 其它模块用
# =====================================================================

static func load_avatar() -> Dictionary:
    """从 saved_logs/avatar.json 读 avatar
    - 文件不存在 → 返回 {} (空 dict, 表示"未捏脸", main.gd 据此显示捏脸 UI)
    - 文件存在但字段缺失 → 用 default 补齐
    - 解析失败 → 返回 {} (强制重新捏脸)
    """
    var default := {
        "hair": "spike", "skin": "medium", "shirt": "red",
        "pants": "blue", "accessory": "none",
    }
    if not FileAccess.file_exists(AVATAR_PATH):
        return {}
    var f := FileAccess.open(AVATAR_PATH, FileAccess.READ)
    if f == null:
        return {}
    var json := JSON.new()
    if json.parse(f.get_as_text()) != OK:
        return {}
    f.close()
    var data: Dictionary = json.data
    # 字段缺失用 default 补
    for k in default:
        if not data.has(k):
            data[k] = default[k]
    return data
