extends Node2D
class_name Player
# Player - 角色容器, 包含 4 种 transport sprite, 通过 switch_transport() 切换
#
# 公开 API:
#   build(tile_size) -> void            # 初始化所有 sprite
#   apply_avatar(avatar: Dictionary) -> void   # 用 avatar 配置重画 walking sprite
#   switch_to(transport: String)        # 切换可见 sprite, 无 tween (transport.gd 处理淡入淡出)
#   get_current() -> String             # 返回当前 transport 名
#   get_eye_node() -> Node              # 朝向指示点 (给 _update_facing_direction 用)

const PALETTE := {"player": Color8(242, 204, 44), "skin": Color8(242, 191, 140)}

# avatar 配方 (跟 avatar_builder.gd 的 OPTIONS 同步)
# shape parts: [x, y, w, h]  (相对中心, 1px 单位)
const AVATAR_PARTS := {
    "hair": [
        {"id": "spike", "name": "尖发", "color": Color8(50, 30, 20),
         "parts": [{"x": -5, "y": -10, "w": 10, "h": 3},
                   {"x": -3, "y": -13, "w": 2, "h": 3},
                   {"x": 1, "y": -13, "w": 2, "h": 3}]},
        {"id": "bob", "name": "波波头", "color": Color8(120, 70, 30),
         "parts": [{"x": -5, "y": -10, "w": 10, "h": 4},
                   {"x": -7, "y": -6, "w": 2, "h": 4},
                   {"x": 5, "y": -6, "w": 2, "h": 4}]},
        {"id": "bald", "name": "光头", "color": Color8(200, 150, 100),
         "parts": [{"x": -5, "y": -10, "w": 10, "h": 2}]},
    ],
    "skin": [
        {"id": "light", "name": "白皮肤", "color": Color8(245, 215, 175), "parts": []},
        {"id": "medium", "name": "黄皮肤", "color": Color8(230, 190, 140), "parts": []},
        {"id": "dark", "name": "深皮肤", "color": Color8(160, 110, 70), "parts": []},
    ],
    "shirt": [
        {"id": "red", "name": "红 T 恤", "color": Color8(220, 60, 60), "parts": [{"x": -5, "y": -2, "w": 10, "h": 5}]},
        {"id": "blue", "name": "蓝 T 恤", "color": Color8(60, 110, 200), "parts": [{"x": -5, "y": -2, "w": 10, "h": 5}]},
        {"id": "white", "name": "白衬衫", "color": Color8(245, 245, 245), "parts": [{"x": -5, "y": -2, "w": 10, "h": 5}]},
    ],
    "pants": [
        {"id": "blue", "name": "蓝裤", "color": Color8(50, 80, 150), "parts": [{"x": -5, "y": 3, "w": 10, "h": 5}]},
        {"id": "black", "name": "黑裤", "color": Color8(40, 40, 50), "parts": [{"x": -5, "y": 3, "w": 10, "h": 5}]},
    ],
    "accessory": [
        {"id": "none", "name": "无", "color": Color.WHITE, "parts": []},
        {"id": "glasses", "name": "眼镜", "color": Color8(30, 30, 30),
         "parts": [{"x": -4, "y": -6, "w": 3, "h": 2},
                   {"x": 1, "y": -6, "w": 3, "h": 2},
                   {"x": -1, "y": -5, "w": 2, "h": 1}]},
    ],
}

var _sprites: Dictionary = {}  # {"walking": Node2D, "driving": ..., "transit": ..., "bicycling": ...}
var _current: String = "walking"
var tile_size: int = 16
var _avatar: Dictionary = {}  # 当前 avatar 配置


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


func apply_avatar(avatar: Dictionary) -> void:
    """用 avatar 配置重画 walking sprite (其它 sprite 暂不重画, P2 阶段)
    avatar: {hair, skin, shirt, pants, accessory}
    """
    _avatar = avatar
    if not _sprites.has("walking"):
        return
    var walk: Node2D = _sprites["walking"]
    # 清理现有 (保留 Eye 因为朝向用)
    for child in walk.get_children():
        if child.name == "Eye":
            continue
        child.queue_free()
    # 顺序: pants -> skin -> shirt -> hair -> accessory
    _avatar_draw_layer(walk, "pants")
    _avatar_draw_layer(walk, "skin")
    _avatar_draw_layer(walk, "shirt")
    _avatar_draw_layer(walk, "hair")
    _avatar_draw_layer(walk, "accessory")


func _avatar_draw_layer(walk: Node2D, layer_id: String) -> void:
    var opt_id: String = _avatar.get(layer_id, "")
    if opt_id == "":
        return
    var opt: Dictionary = _get_avatar_option(layer_id, opt_id)
    if opt.is_empty():
        return
    for part in opt["parts"]:
        var rect := ColorRect.new()
        rect.color = opt["color"]
        rect.size = Vector2(part["w"], part["h"])
        rect.position = Vector2(part["x"] - 8, part["y"] - 8)
        rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
        walk.add_child(rect)


func _get_avatar_option(layer_id: String, opt_id: String) -> Dictionary:
    for opt in AVATAR_PARTS.get(layer_id, []):
        if opt["id"] == opt_id:
            return opt
    return {}


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
