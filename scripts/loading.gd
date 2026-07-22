extends Node
class_name BakeLoadingScene
# BakeLoadingScene - 启动时仪式感动画 (~5 秒)
#
# 视觉序列 (GBA 宝可梦风格):
#   0.0s  黑屏
#   0.5s  标题 "LIFE LOG RPG" 淡入
#   1.0s  副标题 "Inserting cartridge..." 打字机效果
#   1.5s  卡带图标从下方滑入
#   2.0s  倒带进度条 0% -> 100% (2.5 秒)
#   4.5s  "▶ READY" 闪烁
#   5.5s  整个淡出, 发 finished 信号
#
# 用法:
#   var loading = BakeLoadingScene.new()
#   add_child(loading)
#   loading.finished.connect(_on_loading_done)
#   loading.play()

signal finished

var _canvas: CanvasLayer
var _tween: Tween


func play() -> void:
    _canvas = CanvasLayer.new()
    _canvas.layer = 200
    add_child(_canvas)

    # ---- 背景 (GBA 蓝紫) ----
    var bg := ColorRect.new()
    bg.name = "BG"
    bg.color = Color8(20, 30, 50)
    bg.size = Vector2(1280, 720)
    _canvas.add_child(bg)

    # ---- 标题 "LIFE LOG RPG" ----
    var title := Label.new()
    title.name = "Title"
    title.text = "LIFE LOG RPG"
    title.add_theme_color_override("font_color", Color8(255, 220, 100))
    title.add_theme_color_override("font_outline_color", Color8(60, 30, 0))
    title.add_theme_constant_override("outline_size", 4)
    title.add_theme_font_size_override("font_size", 64)
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    title.position = Vector2(0, 100)
    title.size = Vector2(1280, 100)
    title.modulate.a = 0.0
    _canvas.add_child(title)

    # ---- 副标题 (打字机) ----
    var subtitle := Label.new()
    subtitle.name = "Subtitle"
    subtitle.text = ""
    subtitle.add_theme_color_override("font_color", Color8(180, 180, 180))
    subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    subtitle.position = Vector2(0, 220)
    subtitle.size = Vector2(1280, 30)
    subtitle.add_theme_font_size_override("font_size", 20)
    _canvas.add_child(subtitle)

    # ---- 卡带 (深灰色) ----
    var cart := ColorRect.new()
    cart.name = "Cart"
    cart.color = Color8(40, 40, 50)
    cart.size = Vector2(280, 180)
    cart.position = Vector2(500, 320)
    cart.modulate.a = 0.0
    cart.position.y = 720  # 从屏幕下方
    _canvas.add_child(cart)

    # 卡带边框
    var cart_border := ColorRect.new()
    cart_border.color = Color8(80, 80, 90)
    cart_border.size = Vector2(280, 6)
    cart_border.position = Vector2(500, 320)
    cart_border.modulate.a = 0.0
    _canvas.add_child(cart_border)
    var cart_border_bottom := ColorRect.new()
    cart_border_bottom.color = Color8(80, 80, 90)
    cart_border_bottom.size = Vector2(280, 6)
    cart_border_bottom.position = Vector2(500, 494)
    cart_border_bottom.modulate.a = 0.0
    _canvas.add_child(cart_border_bottom)

    # 卡带标签
    var cart_label := Label.new()
    cart_label.name = "CartLabel"
    cart_label.text = "LIFE LOG"
    cart_label.add_theme_color_override("font_color", Color8(200, 200, 100))
    cart_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    cart_label.position = Vector2(500, 370)
    cart_label.size = Vector2(280, 30)
    cart_label.add_theme_font_size_override("font_size", 24)
    cart_label.modulate.a = 0.0
    _canvas.add_child(cart_label)

    # 灰色拉条 (GBA 卡带的金属触点)
    var cart_strip := ColorRect.new()
    cart_strip.color = Color8(120, 120, 130)
    cart_strip.size = Vector2(140, 40)
    cart_strip.position = Vector2(570, 460)
    cart_strip.modulate.a = 0.0
    _canvas.add_child(cart_strip)

    # ---- 倒带进度条 (背景 + 填充) ----
    var progress_bg := ColorRect.new()
    progress_bg.name = "ProgressBG"
    progress_bg.color = Color8(50, 50, 60)
    progress_bg.size = Vector2(400, 12)
    progress_bg.position = Vector2(440, 560)
    _canvas.add_child(progress_bg)
    var progress_fill := ColorRect.new()
    progress_fill.name = "ProgressFill"
    progress_fill.color = Color8(100, 220, 100)
    progress_fill.size = Vector2(0, 12)
    progress_fill.position = Vector2(440, 560)
    _canvas.add_child(progress_fill)

    # ---- READY 文字 ----
    var ready := Label.new()
    ready.name = "Ready"
    ready.text = "▶ READY ▶ PLAY"
    ready.add_theme_color_override("font_color", Color8(100, 255, 100))
    ready.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    ready.position = Vector2(0, 610)
    ready.size = Vector2(1280, 30)
    ready.add_theme_font_size_override("font_size", 28)
    ready.modulate.a = 0.0
    _canvas.add_child(ready)

    # ---- Tween 序列 ----
    _tween = create_tween()
    _tween.set_parallel(false)

    # 0.0 -> 0.5: 标题淡入
    _tween.tween_property(title, "modulate:a", 1.0, 0.5)

    # 0.5 -> 1.5: 打字机 (边写边显示)
    _tween.tween_callback(func(): _type_text(subtitle, "Inserting cartridge...", 0.04))
    _tween.tween_interval(1.0)

    # 1.5 -> 2.0: 卡带从下方滑入
    _tween.tween_property(cart, "position:y", 320.0, 0.5).set_trans(Tween.TRANS_CUBIC)
    _tween.tween_property(cart, "modulate:a", 1.0, 0.3)
    _tween.tween_property(cart_border, "modulate:a", 1.0, 0.3)
    _tween.tween_property(cart_border_bottom, "modulate:a", 1.0, 0.3)
    _tween.tween_property(cart_label, "modulate:a", 1.0, 0.3)
    _tween.tween_property(cart_strip, "modulate:a", 1.0, 0.3)

    # 2.0 -> 4.5: 倒带进度条 0% -> 100%
    _tween.tween_property(progress_fill, "size:x", 400.0, 2.5)

    # 4.5 -> 5.0: READY 淡入
    _tween.tween_property(ready, "modulate:a", 1.0, 0.5)
    _tween.tween_interval(0.8)

    # 5.8 -> 6.3: 整个淡出
    _tween.tween_property(bg, "modulate:a", 0.0, 0.5)
    _tween.tween_callback(func():
        if _canvas:
            _canvas.queue_free()
        finished.emit()
    )


func _type_text(label: Label, text: String, char_delay: float) -> void:
    var t := create_tween()
    for i in range(text.length() + 1):
        var partial: String = text.substr(0, i)
        t.tween_callback(func(): label.text = partial)
        t.tween_interval(char_delay)
