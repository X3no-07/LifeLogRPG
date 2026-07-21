extends Node2D
class_name WorldBuilder
# WorldBuilder - 地图层 (TilemapLayer 模拟 + 路径线)
#
# 用法:
#   var world = WorldBuilder.new()
#   add_child(world)
#   world.build(loader)   # 传入 LogLoader
#
# 输出节点树:
#   WorldBuilder (Node2D)
#   ├── Background (ColorRect, z=-100)
#   ├── TileMapLayer (Node2D, 含所有格子 ColorRect)
#   ├── PathOverlay (Node2D, 含 Line2D + waypoint dots)
#   └── NPCs (Node2D, 由 NpcSystem 填充)

const PALETTE := {
    "grass":   Color8(77, 140, 71),
    "road":    Color8(107, 107, 115),
    "road_dk": Color8(71, 71, 77),
    "building":Color8(140, 107, 77),
    "water":   Color8(51, 102, 179),
    "tree":    Color8(26, 102, 38),
    "sky":     Color8(38, 51, 77),
    "path":    Color8(244, 102, 25),
}

var tile_size: int = 16
var grid_w: int = 80
var grid_h: int = 60
var tilemap: Node2D
var path_overlay: Node2D
var npc_layer: Node2D


func build(loader: LogLoader) -> void:
    tile_size = loader.get_tile_size()
    grid_w = loader.get_grid_width()
    grid_h = loader.get_grid_height()
    # 背景
    var bg := ColorRect.new()
    bg.color = PALETTE["sky"]
    bg.size = Vector2(grid_w * tile_size, grid_h * tile_size)
    bg.position = Vector2.ZERO
    bg.z_index = -100
    bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(bg)

    # TileMap
    tilemap = Node2D.new()
    tilemap.name = "TileMap"
    add_child(tilemap)
    var grid: Array = loader.get_grid()
    for y in grid_h:
        if y >= grid.size():
            break
        var row: Array = grid[y]
        for x in grid_w:
            if x >= row.size():
                break
            var cell_type: int = int(row[x])
            var rect := ColorRect.new()
            rect.color = _color_for_cell(cell_type)
            rect.size = Vector2(tile_size, tile_size)
            rect.position = Vector2(x * tile_size, y * tile_size)
            rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
            tilemap.add_child(rect)

    # 路径线
    path_overlay = Node2D.new()
    path_overlay.name = "PathOverlay"
    add_child(path_overlay)
    _draw_path(loader.get_waypoints())

    # NPC 层 (NpcSystem 用)
    npc_layer = Node2D.new()
    npc_layer.name = "NPCs"
    add_child(npc_layer)


func _draw_path(waypoints: Array) -> void:
    if waypoints.size() < 2:
        return
    var line := Line2D.new()
    line.width = 2.0
    line.default_color = PALETTE["path"]
    for wp in waypoints:
        line.add_point(Vector2(int(wp.get("x", 0)) * tile_size + tile_size / 2.0,
                               int(wp.get("y", 0)) * tile_size + tile_size / 2.0))
    path_overlay.add_child(line)
    for wp in waypoints:
        var dot := ColorRect.new()
        dot.color = Color.WHITE
        dot.size = Vector2(4, 4)
        dot.position = Vector2(int(wp.get("x", 0)) * tile_size + tile_size / 2.0 - 2,
                               int(wp.get("y", 0)) * tile_size + tile_size / 2.0 - 2)
        path_overlay.add_child(dot)


func _color_for_cell(t: int) -> Color:
    match t:
        0: return PALETTE["grass"]
        1: return PALETTE["road"]
        2: return PALETTE["building"]
        3: return PALETTE["water"]
        4: return PALETTE["tree"]
        _: return PALETTE["grass"]
