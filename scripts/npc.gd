extends Node
class_name NpcSystem
# NpcSystem - 在 player 旁边显示 NPC 像素块 + 名字 tag
#
# 用法:
#   var npcs = NpcSystem.new()
#   npcs.setup(npc_layer, tile_size)
#   npcs.update(current_time, dialogs, player_position)
#
# 行为:
#   - 当前 t 落在某条 dialog 的 [t, t+3s] 区间内 且 speaker != "Me", 显示该 NPC
#   - 否则隐藏

const NPC_PALETTE: Array[Color] = [
    Color8(50, 150, 220), Color8(220, 130, 50), Color8(150, 50, 200),
    Color8(80, 200, 100), Color8(220, 50, 150), Color8(180, 180, 50),
    Color8(50, 200, 200),
]

var npc_layer: Node2D
var tile_size: int = 16
var _current: Node2D = null


func setup(p_layer: Node2D, p_tile_size: int) -> void:
    npc_layer = p_layer
    tile_size = p_tile_size


func update(current_time: float, dialogs: Array, player_pos: Vector2) -> void:
    if dialogs.is_empty() or npc_layer == null:
        _hide()
        return
    var speaker := ""
    for d in dialogs:
        var t: float = float(d.get("t", 0))
        if current_time >= t and current_time <= t + 3.0:
            var s: String = String(d.get("speaker", ""))
            if s != "" and s != "Me" and s != "我":
                speaker = s
                break
    if speaker == "":
        _hide()
        return
    var label: Label = null
    if _current:
        label = _current.get_node_or_null("NameTag")
    if label == null or label.text != speaker:
        _show(speaker)
    if _current:
        _current.global_position = player_pos


func _show(speaker: String) -> void:
    _hide()
    var npc := Node2D.new()
    npc.name = "NPC"
    npc.z_index = 5
    var s := float(tile_size)
    var body := ColorRect.new()
    body.color = _get_color(speaker)
    body.size = Vector2(s * 0.5, s * 0.6)
    body.position = Vector2(s * 0.5, -s * 0.3)
    body.mouse_filter = Control.MOUSE_FILTER_IGNORE
    npc.add_child(body)
    var head := ColorRect.new()
    head.color = Color8(242, 191, 140)
    head.size = Vector2(s * 0.4, s * 0.35)
    head.position = Vector2(s * 0.55, -s * 0.65)
    head.mouse_filter = Control.MOUSE_FILTER_IGNORE
    npc.add_child(head)
    var name_label := Label.new()
    name_label.name = "NameTag"
    name_label.text = speaker
    name_label.add_theme_color_override("font_color", Color.WHITE)
    name_label.add_theme_color_override("font_outline_color", Color.BLACK)
    name_label.add_theme_constant_override("outline_size", 3)
    name_label.add_theme_font_size_override("font_size", 11)
    name_label.position = Vector2(s * 0.3, -s * 1.05)
    name_label.size = Vector2(s * 1.6, 16)
    name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    npc.add_child(name_label)
    npc_layer.add_child(npc)
    _current = npc


func _hide() -> void:
    if _current and is_instance_valid(_current):
        _current.queue_free()
    _current = null


func _get_color(speaker: String) -> Color:
    var h: int = 0
    for c in speaker:
        h = (h * 31 + ord(c)) % 1000000
    return NPC_PALETTE[abs(h) % NPC_PALETTE.size()]
