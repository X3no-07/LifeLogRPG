extends Node2D
class_name Player
# Player - 角色容器, 包含 4 种 transport sprite, 通过 switch_transport() 切换
#
# 公开 API:
#   build(tile_size) -> void            # 初始化所有 sprite
#   switch_to(transport: String)        # 切换可见 sprite, 无 tween (transport.gd 处理淡入淡出)
#   get_current() -> String             # 返回当前 transport 名
#   get_eye_node() -> Node              # 朝向指示点 (给 _update_facing_direction 用)

const PALETTE := {"player": Color8(242, 204, 44), "skin": Color8(242, 191, 140)}

var _sprites: Dictionary = {}  # {"walking": Node2D, "driving": ..., "transit": ..., "bicycling": ...}
var _current: String = "walking"
var tile_size: int = 16


func build(p_tile_size: int) -> void:
    tile_size = p_tile_size
    _sprites["walking"] = _create_walk()
    _sprites["driving"] = _create_drive()
    _sprites["transit"] = _create_transit()
    _sprites["bicycling"] = _create_bike()
    for k in _sprites:
        var sp: Node2D = _sprites[k]
        sp.visible = false
        add_child(sp)
    _sprites["walking"].visible = true
    _current = "walking"


func switch_to(transport: String) -> bool:
    """切换 transport, 返回是否真的换了 (false = 已经是这个)"""
    if transport == _current:
        return false
    if not _sprites.has(transport):
        return false
    if _sprites.has(_current):
        _sprites[_current].visible = false
    _sprites[transport].visible = true
    _current = transport
    return true


func get_current() -> String:
    return _current


func get_eye_node() -> Node:
    var sp: Node2D = _sprites.get("walking")
    if sp:
        return sp.get_node_or_null("Eye")
    return null


# ---------- sprite 工厂 ----------

func _create_walk() -> Node2D:
    var root := Node2D.new()
    root.name = "WalkSprite"
    var s := float(tile_size)
    var body := ColorRect.new()
    body.color = PALETTE["player"]
    body.size = Vector2(s * 0.6, s * 0.7)
    body.position = Vector2(-s * 0.3, -s * 0.35)
    body.mouse_filter = Control.MOUSE_FILTER_IGNORE
    root.add_child(body)
    var head := ColorRect.new()
    head.color = PALETTE["skin"]
    head.size = Vector2(s * 0.5, s * 0.4)
    head.position = Vector2(-s * 0.25, -s * 0.75)
    head.mouse_filter = Control.MOUSE_FILTER_IGNORE
    root.add_child(head)
    var eye := ColorRect.new()
    eye.name = "Eye"
    eye.color = Color.BLACK
    eye.size = Vector2(2, 2)
    eye.position = Vector2(s * 0.05, -s * 0.6)
    root.add_child(eye)
    return root


func _create_drive() -> Node2D:
    var root := Node2D.new()
    root.name = "DriveSprite"
    var s := float(tile_size)
    var body := ColorRect.new()
    body.color = Color8(220, 50, 50)
    body.size = Vector2(s * 1.4, s * 0.55)
    body.position = Vector2(-s * 0.7, -s * 0.3)
    body.mouse_filter = Control.MOUSE_FILTER_IGNORE
    root.add_child(body)
    var roof := ColorRect.new()
    roof.color = Color8(150, 30, 30)
    roof.size = Vector2(s * 0.8, s * 0.3)
    roof.position = Vector2(-s * 0.4, -s * 0.55)
    roof.mouse_filter = Control.MOUSE_FILTER_IGNORE
    root.add_child(roof)
    var window := ColorRect.new()
    window.color = Color8(150, 200, 240)
    window.size = Vector2(s * 0.7, s * 0.2)
    window.position = Vector2(-s * 0.35, -s * 0.5)
    window.mouse_filter = Control.MOUSE_FILTER_IGNORE
    root.add_child(window)
    for ox in [-s * 0.5, s * 0.3]:
        var wheel := ColorRect.new()
        wheel.color = Color.BLACK
        wheel.size = Vector2(s * 0.25, s * 0.2)
        wheel.position = Vector2(ox, s * 0.15)
        wheel.mouse_filter = Control.MOUSE_FILTER_IGNORE
        root.add_child(wheel)
    var headlight := ColorRect.new()
    headlight.color = Color8(255, 230, 100)
    headlight.size = Vector2(s * 0.1, s * 0.1)
    headlight.position = Vector2(s * 0.6, -s * 0.2)
    root.add_child(headlight)
    return root


func _create_transit() -> Node2D:
    var root := Node2D.new()
    root.name = "TransitSprite"
    var s := float(tile_size)
    var body := ColorRect.new()
    body.color = Color8(80, 130, 180)
    body.size = Vector2(s * 1.8, s * 0.7)
    body.position = Vector2(-s * 0.9, -s * 0.4)
    body.mouse_filter = Control.MOUSE_FILTER_IGNORE
    root.add_child(body)
    var front := ColorRect.new()
    front.color = Color8(40, 70, 110)
    front.size = Vector2(s * 0.2, s * 0.7)
    front.position = Vector2(s * 0.7, -s * 0.4)
    root.add_child(front)
    for i in range(3):
        var win := ColorRect.new()
        win.color = Color8(200, 230, 255)
        win.size = Vector2(s * 0.3, s * 0.25)
        win.position = Vector2(-s * 0.7 + i * s * 0.45, -s * 0.3)
        root.add_child(win)
    var headlight := ColorRect.new()
    headlight.color = Color8(255, 240, 100)
    headlight.size = Vector2(s * 0.1, s * 0.15)
    headlight.position = Vector2(s * 0.85, -s * 0.15)
    root.add_child(headlight)
    return root


func _create_bike() -> Node2D:
    var root := Node2D.new()
    root.name = "BikeSprite"
    var s := float(tile_size)
    var frame := ColorRect.new()
    frame.color = Color8(50, 50, 50)
    frame.size = Vector2(s * 1.2, s * 0.15)
    frame.position = Vector2(-s * 0.6, s * 0.05)
    root.add_child(frame)
    for ox in [-s * 0.55, s * 0.4]:
        var wheel := ColorRect.new()
        wheel.color = Color.BLACK
        wheel.size = Vector2(s * 0.3, s * 0.3)
        wheel.position = Vector2(ox, s * 0.05)
        root.add_child(wheel)
    var body := ColorRect.new()
    body.color = PALETTE["player"]
    body.size = Vector2(s * 0.4, s * 0.5)
    body.position = Vector2(-s * 0.2, -s * 0.45)
    root.add_child(body)
    var head := ColorRect.new()
    head.color = PALETTE["skin"]
    head.size = Vector2(s * 0.35, s * 0.3)
    head.position = Vector2(-s * 0.175, -s * 0.7)
    root.add_child(head)
    return root
