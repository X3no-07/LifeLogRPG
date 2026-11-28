extends Control

signal run_requested(mode: String, input: String, duration: float, amap_key: String, deepseek_key: String, city: String)
signal sample_requested
signal replay_requested
signal cancel_requested
signal place_search_requested(index: int, query: String)

const EXAMPLE_COORDS := "116.41000000,39.90900000;116.41262098,39.91029054"
const INK := Color("#13232c")
const NIGHT := Color("#101c23")
const PANEL := Color("#172a33")
const FIELD := Color("#14242d")
const EDGE := Color("#36515b")
const WHITE := Color("#f2eee2")
const MUTED := Color("#adc0c1")
const MINT := Color("#97debd")
const GOLD := Color("#f4d17d")
const ERROR := Color("#ffad9e")

var _mode := "coords"
var _busy := false
var _has_replay := false
var _layout: BoxContainer
var _intro: VBoxContainer
var _illustration: Control
var _form: PanelContainer
var _coords_tab: Button
var _diary_tab: Button
var _example: Button
var _coords: TextEdit
var _diary: TextEdit
var _keys: HBoxContainer
var _amap: LineEdit
var _deepseek: LineEdit
var _city: LineEdit
var _duration: SpinBox
var _run: Button
var _sample: Button
var _replay: Button
var _hint: Label
var _status: Label
var _progress: ProgressBar
var _cancel: Button
var _place_section: VBoxContainer
var _place_fields: Array[LineEdit] = []
var _selected_places: Array[Dictionary] = [{}, {}]
var _place_choices: VBoxContainer
var _place_message: Label


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var app_theme := Theme.new()
    app_theme.default_font_size = 16
    app_theme.set_color("font_color", "Label", WHITE)
    theme = app_theme

    var background := ColorRect.new()
    background.color = NIGHT
    background.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(background)
    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

    var scroll := ScrollContainer.new()
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    add_child(scroll)
    scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

    var margins := MarginContainer.new()
    margins.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    margins.size_flags_vertical = Control.SIZE_EXPAND_FILL
    margins.add_theme_constant_override("margin_left", 28)
    margins.add_theme_constant_override("margin_right", 28)
    margins.add_theme_constant_override("margin_top", 28)
    margins.add_theme_constant_override("margin_bottom", 28)
    scroll.add_child(margins)
    var center := CenterContainer.new()
    margins.add_child(center)
    _layout = BoxContainer.new()
    center.add_child(_layout)

    _build_intro()
    _build_form()
    resized.connect(_resize_layout)
    _resize_layout()
    _select_mode("coords")
    _sync_controls()


func _build_intro() -> void:
    _intro = VBoxContainer.new()
    _intro.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    _intro.add_theme_constant_override("separation", 14)
    _layout.add_child(_intro)
    _intro.add_child(_label("Life Log RPG", 46, WHITE))
    var subtitle := _label("把真实路线和生活日记变成像素回放。", 17, MUTED)
    subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    _intro.add_child(subtitle)

    _illustration = Control.new()
    _illustration.custom_minimum_size.y = 206
    _illustration.mouse_filter = Control.MOUSE_FILTER_IGNORE
    _illustration.draw.connect(_draw_route_preview)
    _illustration.resized.connect(_illustration.queue_redraw)
    _intro.add_child(_illustration)

    _sample = _button("播放内置路线")
    _sample.pressed.connect(func() -> void: sample_requested.emit())
    _intro.add_child(_sample)
    _replay = _button("播放最近生成的路线")
    _replay.pressed.connect(func() -> void: replay_requested.emit())
    _intro.add_child(_replay)


func _build_form() -> void:
    _form = PanelContainer.new()
    var panel := _surface(PANEL, EDGE, 11, Vector2(28, 25))
    _form.add_theme_stylebox_override("panel", panel)
    _form.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    _layout.add_child(_form)

    var body := VBoxContainer.new()
    body.add_theme_constant_override("separation", 14)
    _form.add_child(body)
    body.add_child(_label("生成回放", 30, WHITE))

    var tabs := HBoxContainer.new()
    tabs.add_theme_constant_override("separation", 9)
    body.add_child(tabs)
    var mode_group := ButtonGroup.new()
    _coords_tab = _mode_button("经纬度", mode_group)
    _diary_tab = _mode_button("中文日记", mode_group)
    _coords_tab.pressed.connect(_select_mode.bind("coords"))
    _diary_tab.pressed.connect(_select_mode.bind("text"))
    tabs.add_child(_coords_tab)
    tabs.add_child(_diary_tab)

    _hint = _label("", 15, MUTED)
    _hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    body.add_child(_hint)
    _coords = _text_area("经度,纬度;经度,纬度")
    _diary = _text_area("例如：下午从王府井喜悦购物中心走到王府井书店。")
    body.add_child(_coords)
    body.add_child(_diary)
    _coords.text_changed.connect(_sync_controls)
    _diary.text_changed.connect(_sync_controls)

    _keys = HBoxContainer.new()
    _keys.add_theme_constant_override("separation", 10)
    body.add_child(_keys)
    _city = _form_field("所在城市", false)
    _city.text = "北京"
    _city.max_length = 64
    _amap = _form_field("高德 Key", true)
    _deepseek = _form_field("DeepSeek Key", true)
    _build_place_search(body)

    var actions := HBoxContainer.new()
    actions.alignment = BoxContainer.ALIGNMENT_BEGIN
    actions.add_theme_constant_override("separation", 12)
    body.add_child(actions)
    actions.add_child(_label("回放秒数", 15, WHITE))
    _duration = SpinBox.new()
    _duration.custom_minimum_size.x = 88
    _duration.min_value = 1
    _duration.max_value = 3600
    _duration.value = 30
    _duration.get_line_edit().alignment = HORIZONTAL_ALIGNMENT_CENTER
    _style_line_edit(_duration.get_line_edit())
    actions.add_child(_duration)
    var spacer := Control.new()
    spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    actions.add_child(spacer)
    _example = _button("填入王府井坐标")
    _example.pressed.connect(_fill_example)
    actions.add_child(_example)

    _run = _button("生成并播放", true)
    _run.custom_minimum_size.y = 48
    _run.pressed.connect(_submit)
    body.add_child(_run)

    _progress = ProgressBar.new()
    _progress.custom_minimum_size.y = 4
    _progress.show_percentage = false
    _progress.indeterminate = true
    _progress.add_theme_stylebox_override("background", _surface(FIELD, FIELD, 2, Vector2.ZERO))
    _progress.add_theme_stylebox_override("fill", _surface(MINT, MINT, 2, Vector2.ZERO))
    body.add_child(_progress)
    _status = _label("", 15, MUTED)
    _status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    _status.hide()
    body.add_child(_status)
    _cancel = _button("取消生成")
    _cancel.pressed.connect(func() -> void: cancel_requested.emit())
    body.add_child(_cancel)


func _build_place_search(body: VBoxContainer) -> void:
    _place_section = VBoxContainer.new()
    body.add_child(_place_section)
    var fields := HBoxContainer.new()
    fields.add_theme_constant_override("separation", 10)
    _place_section.add_child(fields)
    for index in range(2):
        var field := LineEdit.new()
        field.placeholder_text = "搜索起点" if index == 0 else "搜索终点"
        field.max_length = 120
        field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        _style_line_edit(field)
        fields.add_child(field)
        _place_fields.append(field)
        field.text_changed.connect(_place_edited.bind(index))
        field.focus_entered.connect(_search_unselected.bind(index))
    _city.text_changed.connect(func(_value: String) -> void:
        _selected_places = [{}, {}]
        place_search_requested.emit(-1, "")
        show_place_choices(-1, [], "")
        _sync_controls()
    )
    _amap.text_changed.connect(func(_value: String) -> void:
        place_search_requested.emit(-1, "")
        show_place_choices(-1, [], "")
    )
    _place_message = _label("", 14, MUTED)
    _place_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    _place_section.add_child(_place_message)
    _place_message.hide()
    _place_choices = VBoxContainer.new()
    _place_section.add_child(_place_choices)


func _place_edited(value: String, index: int) -> void:
    _selected_places[index] = {}
    place_search_requested.emit(index, value.strip_edges())
    _sync_controls()


func _search_unselected(index: int) -> void:
    if _selected_places[index].is_empty() and not _place_fields[index].text.is_empty():
        place_search_requested.emit(index, _place_fields[index].text.strip_edges())


func show_place_choices(index: int, choices: Array, message: String) -> void:
    for child in _place_choices.get_children():
        _place_choices.remove_child(child)
        child.queue_free()
    _place_message.text = message
    _place_message.visible = not message.is_empty()
    for choice: Dictionary in choices:
        var address := str(choice.get("address", ""))
        var label := str(choice["name"])
        if not address.is_empty():
            label += " · " + address
        var button := _button(label)
        button.alignment = HORIZONTAL_ALIGNMENT_LEFT
        button.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
        button.tooltip_text = label
        button.custom_minimum_size.y = 30
        button.pressed.connect(_choose_place.bind(index, choice))
        _place_choices.add_child(button)


func _choose_place(index: int, choice: Dictionary) -> void:
    _selected_places[index] = choice
    _place_fields[index].text = str(choice["name"])
    show_place_choices(-1, [], "")
    if index == 0 and _selected_places[1].is_empty():
        _place_fields[1].grab_focus()
    _sync_controls()


func selected_route_places() -> Array[Dictionary]:
    if _mode == "text" and not _selected_places[0].is_empty() and not _selected_places[1].is_empty():
        return _selected_places.duplicate()
    return []


func _ready_to_generate() -> bool:
    if _mode == "text" and _place_fields.any(func(field: LineEdit) -> bool: return not field.text.strip_edges().is_empty()):
        return not selected_route_places().is_empty()
    return not _current_input().is_empty()


func _resize_layout() -> void:
    var stacked := size.x < 855
    _layout.vertical = stacked
    _layout.custom_minimum_size.x = maxf(0, minf(size.x - 60, 1080))
    _layout.add_theme_constant_override("separation", 23 if stacked else 42)
    _intro.custom_minimum_size.x = 0 if stacked else 326
    _illustration.visible = not stacked


func _select_mode(mode: String) -> void:
    _mode = mode
    var coords_mode := mode == "coords"
    _coords_tab.set_pressed_no_signal(coords_mode)
    _diary_tab.set_pressed_no_signal(not coords_mode)
    _coords.visible = coords_mode
    _diary.visible = not coords_mode
    _keys.visible = not coords_mode
    _place_section.visible = not coords_mode
    _example.visible = coords_mode
    if coords_mode:
        place_search_requested.emit(-1, "")
        _hint.text = "输入至少两个高德 GCJ-02 坐标。用英文分号隔开，联网取图无需 Key。"
    else:
        _hint.text = "可直接写日记，也可搜索并点选起点和终点。日记由 DeepSeek 生成回放文案。"
    _sync_controls()


func _current_input() -> String:
    return (_coords.text if _mode == "coords" else _diary.text).strip_edges()


func _fill_example() -> void:
    _coords.text = EXAMPLE_COORDS
    _sync_controls()


func _submit() -> void:
    if _busy or not _ready_to_generate():
        return
    _duration.apply()
    var input := _current_input()
    var places := selected_route_places()
    if input.is_empty() and not places.is_empty():
        input = "从%s到%s" % [places[0]["name"], places[1]["name"]]
    run_requested.emit(
        _mode, input, _duration.value, _amap.text.strip_edges(),
        _deepseek.text.strip_edges(), _city.text.strip_edges()
    )


func set_busy(busy: bool) -> void:
    _busy = busy
    _sync_controls()


func show_status(value: String, is_error: bool = false) -> void:
    _status.text = value
    _status.add_theme_color_override("font_color", ERROR if is_error else MUTED)
    _status.visible = not value.is_empty()


func set_replay_available(available: bool) -> void:
    _has_replay = available
    _sync_controls()


func _sync_controls() -> void:
    if not is_instance_valid(_progress):
        return
    _run.disabled = _busy or not _ready_to_generate()
    _run.text = "正在生成回放…" if _busy else "生成并播放"
    _coords_tab.disabled = _busy
    _diary_tab.disabled = _busy
    _replay.disabled = not _has_replay
    _example.disabled = _busy
    _coords.editable = not _busy
    _diary.editable = not _busy
    _amap.editable = not _busy
    _deepseek.editable = not _busy
    _city.editable = not _busy
    for field in _place_fields:
        field.editable = not _busy
    _duration.editable = not _busy
    _progress.visible = _busy
    _cancel.visible = _busy
    _cancel.disabled = not _busy


func _form_field(label_text: String, masked: bool) -> LineEdit:
    var box := VBoxContainer.new()
    box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    box.add_theme_constant_override("separation", 5)
    _keys.add_child(box)
    box.add_child(_label(label_text, 15, WHITE))
    var input := LineEdit.new()
    input.secret = masked
    _style_line_edit(input)
    box.add_child(input)
    return input


func _label(value: String, font_size: int, color: Color) -> Label:
    var node := Label.new()
    node.text = value
    node.add_theme_font_size_override("font_size", font_size)
    node.add_theme_color_override("font_color", color)
    return node


func _surface(fill: Color, border: Color, radius: int, padding: Vector2) -> StyleBoxFlat:
    var result := StyleBoxFlat.new()
    result.bg_color = fill
    result.border_color = border
    result.set_border_width_all(1)
    result.set_corner_radius_all(radius)
    result.content_margin_left = padding.x
    result.content_margin_right = padding.x
    result.content_margin_top = padding.y
    result.content_margin_bottom = padding.y
    return result


func _button(value: String, primary: bool = false) -> Button:
    var node := Button.new()
    node.text = value
    node.custom_minimum_size.y = 39
    var normal := GOLD if primary else Color("#203741")
    var foreground := INK if primary else WHITE
    var padding := Vector2(14, 6)
    node.add_theme_stylebox_override("normal", _surface(normal, normal if primary else EDGE, 6, padding))
    node.add_theme_stylebox_override("hover", _surface(normal.lightened(0.10), MINT, 6, padding))
    node.add_theme_stylebox_override("pressed", _surface(MINT, MINT, 6, padding))
    node.add_theme_stylebox_override("disabled", _surface(Color("#213239"), EDGE, 6, padding))
    for state in ["font_color", "font_hover_color", "font_focus_color"]:
        node.add_theme_color_override(state, foreground)
    node.add_theme_color_override("font_pressed_color", INK)
    node.add_theme_color_override("font_disabled_color", Color("#819295"))
    return node


func _mode_button(value: String, group: ButtonGroup) -> Button:
    var node := _button(value)
    node.toggle_mode = true
    node.button_group = group
    node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return node


func _text_area(placeholder: String) -> TextEdit:
    var node := TextEdit.new()
    node.placeholder_text = placeholder
    node.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
    node.custom_minimum_size.y = 99
    node.add_theme_stylebox_override("normal", _surface(FIELD, EDGE, 6, Vector2(11, 9)))
    node.add_theme_stylebox_override("read_only", _surface(FIELD, EDGE, 6, Vector2(11, 9)))
    node.add_theme_color_override("font_color", WHITE)
    node.add_theme_color_override("font_placeholder_color", MUTED)
    return node


func _style_line_edit(node: LineEdit) -> void:
    node.add_theme_stylebox_override("normal", _surface(FIELD, EDGE, 6, Vector2(10, 6)))
    node.add_theme_stylebox_override("read_only", _surface(FIELD, EDGE, 6, Vector2(10, 6)))
    node.add_theme_color_override("font_color", WHITE)


func _draw_route_preview() -> void:
    var size_rect := Rect2(Vector2.ZERO, _illustration.size)
    _illustration.draw_rect(size_rect, Color("#1a3039"))
    _illustration.draw_rect(size_rect.grow(-1), EDGE, false, 1)
    var scale_factor := minf(_illustration.size.x / 326.0, _illustration.size.y / 206.0)
    var shift := (_illustration.size - Vector2(326, 206) * scale_factor) * 0.5
    _illustration.draw_set_transform(shift, 0, Vector2.ONE * scale_factor)

    # A block of stylized streets with the same marker colors as the player.
    for x in range(14, 325, 14):
        for y in range(14, 204, 14):
            _illustration.draw_circle(Vector2(x, y), 1, Color("#2e4951"))
    var street := PackedVector2Array([
        Vector2(26, 154), Vector2(121, 154), Vector2(121, 75),
        Vector2(223, 75), Vector2(223, 40), Vector2(292, 40),
    ])
    _illustration.draw_polyline(street, Color("#4d6864"), 19)
    for roof in [
        Rect2(37, 62, 63, 54), Rect2(146, 105, 65, 57),
        Rect2(242, 80, 48, 52), Rect2(151, 30, 46, 27),
    ]:
        _illustration.draw_rect(Rect2(roof.position + Vector2(0, 6), roof.size), Color("#34484b"))
        _illustration.draw_rect(roof, Color("#506f74"))
        _illustration.draw_line(roof.position + Vector2(7, 7), roof.position + Vector2(roof.size.x - 7, 7),
            Color("#7d9690"), 2)
    _illustration.draw_polyline(street, GOLD, 3)
    _illustration.draw_circle(street[0], 5, MINT)
    _illustration.draw_circle(street[-1], 6, GOLD)
    _illustration.draw_circle(street[-1], 2, INK)
    _illustration.draw_set_transform(Vector2.ZERO)
