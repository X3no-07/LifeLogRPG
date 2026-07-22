extends Node2D
class_name WorldBuilder
# WorldBuilder - 地图层 (TileMap + TileSet + 路径线 + POI + Transit Pin)
#
# P1.1 升级: 用 TileMap + TileSet 替换 ColorRect 循环
#   - 加载 assets/tiles/tile_sheet.png (4x2, 64x32, 8 个 GBA 风格 16x16 tile)
#   - 8 个 cell type -> 8 个 tile (grass/road/building/water/tree/sidewalk/poi/plaza)
#   - TileSet 运行时创建 (避免依赖 .import 文件)
#
# 用法:
#   var world = WorldBuilder.new()
#   add_child(world)
#   world.build(loader)   # 传入 LogLoader
#
# 输出节点树:
#   WorldBuilder (Node2D)
#   ├── Background (ColorRect, z=-100)
#   ├── TileMap (含 TileMapLayer 0, z=0)
#   ├── PathOverlay (Node2D, 含 Line2D + waypoint dots)
#   ├── NPCs (Node2D, 由 NpcSystem 填充)
#   ├── POIs (Node2D, P0.3 POI 标记)
#   └── TransitPins (Node2D, P0.4 端点 pin)

# Tile sheet 路径 (res:// 是 Godot 项目根目录, 跟 project.godot 同级)
const TILE_SHEET_PATH := "res://assets/tiles/tile_sheet.png"
const SHEET_COLS := 4     # 4 列 x 2 行 = 8 tile
const SHEET_ROWS := 2
const TILE_SIZE_PX := 16  # 每个 tile 16x16 像素
# P1.3 室内 icon sheet
const INTERIOR_SHEET_PATH := "res://assets/tiles/interior_sheet.png"
const INTERIOR_SHEET_COLS := 4  # 4 列 x 4 行 = 16 slot (实际 13 个)
const INTERIOR_SHEET_ROWS := 4
# 类别 -> atlas coord (跟 generate_interior_icons.py 的 DRAWERS 顺序一致)
# 0 cafe | 1 restaurant | 2 shop | 3 office | 4 hotel | 5 hospital | 6 bank |
# 7 school | 8 museum | 9 pharmacy | 10 library | 11 fitness | 12 theater
const INTERIOR_ATLAS: Dictionary = {
    "cafe": Vector2i(0, 0), "restaurant": Vector2i(1, 0), "shop": Vector2i(2, 0),
    "office": Vector2i(3, 0), "hotel": Vector2i(0, 1), "hospital": Vector2i(1, 1),
    "bank": Vector2i(2, 1), "school": Vector2i(3, 1), "museum": Vector2i(0, 2),
    "pharmacy": Vector2i(1, 2), "library": Vector2i(2, 2), "fitness": Vector2i(3, 2),
    "theater": Vector2i(0, 3),
}

# 颜色 palette (保留: POI / transit pin / path overlay 还需要)
const PALETTE := {
    "grass":   Color8(77, 140, 71),
    "road":    Color8(107, 107, 115),
    "road_dk": Color8(71, 71, 77),
    "building":Color8(140, 107, 77),
    "water":   Color8(51, 102, 179),
    "tree":    Color8(26, 102, 38),
    "sky":     Color8(38, 51, 77),
    "path":    Color8(244, 102, 25),
    "sidewalk":Color8(200, 200, 200),
    "poi":     Color8(255, 220, 100),
    "plaza":   Color8(220, 200, 150),
    "poi_scenic":  Color8(100, 200, 100),
    "poi_food":    Color8(255, 140, 60),
    "poi_shop":    Color8(200, 100, 220),
    "poi_life":    Color8(80, 180, 220),
    "poi_default": Color8(255, 220, 100),
    "transit_pin_transit": Color8(255, 60, 60),
    "transit_pin_driving": Color8(120, 60, 200),
}

var grid_w: int = 80
var grid_h: int = 60
var tile_size: int = 16
var tilemap: TileMap
var tile_layer: TileMapLayer
var path_overlay: Node2D
var npc_layer: Node2D
var tile_set: TileSet
var interior_set: TileSet          # P1.3 室内 icon 用独立 TileSet (避免跟地形冲突)


# =====================================================================
#  P1.1: TileSet 加载 (程序化, 不依赖 .import 文件)
# =====================================================================

func _init_tile_set() -> void:
    """从 tile_sheet.png 加载, 运行时创建 TileSet
    用 FileAccess + Image.load_png_from_buffer (instance method), 跳过 .import 系统
    """
    if not FileAccess.file_exists(TILE_SHEET_PATH):
        push_error("WorldBuilder: tile sheet not found: " + TILE_SHEET_PATH)
        return
    var f := FileAccess.open(TILE_SHEET_PATH, FileAccess.READ)
    if f == null:
        push_error("WorldBuilder: cannot open " + TILE_SHEET_PATH)
        return
    var bytes := f.get_buffer(f.get_length())
    f.close()
    var img := Image.new()
    var err := img.load_png_from_buffer(bytes)
    if err != OK:
        push_error("WorldBuilder: cannot decode PNG, err=%d" % err)
        return
    var tex := ImageTexture.create_from_image(img)

    tile_set = TileSet.new()
    tile_set.tile_size = Vector2i(TILE_SIZE_PX, TILE_SIZE_PX)

    var atlas := TileSetAtlasSource.new()
    atlas.texture = tex
    atlas.texture_region_size = Vector2i(TILE_SIZE_PX, TILE_SIZE_PX)
    # 创建 8 个 tile (一行 4 个, 2 行)
    for i in range(8):
        var col: int = i % SHEET_COLS
        var row: int = i / SHEET_COLS
        atlas.create_tile(Vector2i(col, row))
    tile_set.add_source(atlas)
    print("[WorldBuilder] TileSet 加载完成: 8 tiles from %s" % TILE_SHEET_PATH)


func _cell_to_atlas(cell_type: int) -> Vector2i:
    """cell_type (0-7) -> atlas coords (col, row)"""
    var ct: int = clamp(cell_type, 0, 7)
    return Vector2i(ct % SHEET_COLS, ct / SHEET_COLS)


# =====================================================================
#  P1.3: 室内 icon TileSet
# =====================================================================

func _init_interior_set() -> void:
    """加载 interior_sheet.png, 运行时建独立 TileSet (用 16x16 source)
    跟地形 TileSet 区分, source id 用 1
    """
    if not FileAccess.file_exists(INTERIOR_SHEET_PATH):
        push_warning("WorldBuilder: interior sheet not found: " + INTERIOR_SHEET_PATH)
        return
    var f := FileAccess.open(INTERIOR_SHEET_PATH, FileAccess.READ)
    if f == null:
        push_warning("WorldBuilder: cannot open " + INTERIOR_SHEET_PATH)
        return
    var bytes := f.get_buffer(f.get_length())
    f.close()
    var img := Image.new()
    var err := img.load_png_from_buffer(bytes)
    if err != OK:
        push_warning("WorldBuilder: cannot decode interior PNG, err=%d" % err)
        return
    var tex := ImageTexture.create_from_image(img)

    interior_set = TileSet.new()
    interior_set.tile_size = Vector2i(TILE_SIZE_PX, TILE_SIZE_PX)

    var atlas := TileSetAtlasSource.new()
    atlas.texture = tex
    atlas.texture_region_size = Vector2i(TILE_SIZE_PX, TILE_SIZE_PX)
    # 创建 13 个 tile (0-12, 跟 INTERIOR_ATLAS 一致)
    for i in range(13):
        var col: int = i % INTERIOR_SHEET_COLS
        var row: int = i / INTERIOR_SHEET_COLS
        atlas.create_tile(Vector2i(col, row))
    interior_set.add_source(atlas)
    print("[WorldBuilder] P1.3 Interior TileSet: 13 tiles from %s" % INTERIOR_SHEET_PATH)


# =====================================================================
#  Build
# =====================================================================

func build(loader) -> void:
    _init_tile_set()
    _init_interior_set()  # P1.3
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

    # TileMap + TileMapLayer (P1.1: 用 TileSet 替换 ColorRect)
    tilemap = TileMap.new()
    tilemap.name = "TileMap"
    tilemap.tile_set = tile_set
    tilemap.z_index = 0
    add_child(tilemap)

    tile_layer = TileMapLayer.new()
    tile_layer.name = "Layer0"
    tile_layer.z_index = 0
    tilemap.add_child(tile_layer)

    # 设 cells
    var grid: Array = loader.get_grid()
    var set_count: int = 0
    for y in range(grid_h):
        if y >= grid.size():
            break
        var row: Array = grid[y]
        for x in range(grid_w):
            if x >= row.size():
                break
            var cell_type: int = int(row[x])
            var atlas_coords: Vector2i = _cell_to_atlas(cell_type)
            tile_layer.set_cell(Vector2i(x, y), 0, atlas_coords)
            set_count += 1
    print("[WorldBuilder] TileMap set %d cells (%dx%d)" % [set_count, grid_w, grid_h])

    # 路径线
    path_overlay = Node2D.new()
    path_overlay.name = "PathOverlay"
    add_child(path_overlay)
    _draw_path(loader.get_waypoints())

    # NPC 层
    npc_layer = Node2D.new()
    npc_layer.name = "NPCs"
    add_child(npc_layer)

    # P0.3: POI 标记
    if loader.get_pois().size() > 0:
        render_pois(loader.get_pois())

    # P0.4: Transit 端点 pin
    if loader.get_transit_markers().size() > 0:
        render_transit_markers(loader.get_transit_markers())

    # P1.2: 建筑高度 (抬高建筑到对应层数高度)
    if loader.get_building_heights().size() > 0:
        render_buildings_with_height(loader.get_building_heights())

    # P1.3: 室内 slots (咖啡厅/办公室/医院/... 画 icon)
    if loader.get_interiors().size() > 0:
        render_interior_slots(loader.get_interiors())


# =====================================================================
#  Path overlay (Line2D + waypoint dots, 跟 P0/P2 一样)
# =====================================================================

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


# =====================================================================
#  P0.3: POI 标记 (保留, 不依赖 cell type)
# =====================================================================

func _poi_color(category: String) -> Color:
    match category:
        "scenic": return PALETTE["poi_scenic"]
        "food":   return PALETTE["poi_food"]
        "shop":   return PALETTE["poi_shop"]
        "life":   return PALETTE["poi_life"]
        _: return PALETTE["poi_default"]


func render_pois(pois: Array) -> void:
    var poi_layer := Node2D.new()
    poi_layer.name = "POIs"
    poi_layer.z_index = 8
    add_child(poi_layer)
    for poi in pois:
        var gx: int = int(poi.get("grid_x", 0))
        var gy: int = int(poi.get("grid_y", 0))
        if gx < 0 or gy < 0 or gx >= grid_w or gy >= grid_h:
            continue
        var category: String = String(poi.get("category", ""))
        var color: Color = _poi_color(category)
        var s := float(tile_size)
        var marker := Node2D.new()
        marker.name = "POI_%s" % String(poi.get("name", ""))
        marker.position = Vector2(gx * s + s * 0.5, gy * s + s * 0.5)
        var dot := ColorRect.new()
        dot.color = color
        dot.size = Vector2(s * 0.7, s * 0.7)
        dot.position = Vector2(-s * 0.35, -s * 0.35)
        dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
        marker.add_child(dot)
        var inner := ColorRect.new()
        inner.color = Color8(255, 255, 255)
        inner.size = Vector2(s * 0.3, s * 0.3)
        inner.position = Vector2(-s * 0.15, -s * 0.15)
        inner.mouse_filter = Control.MOUSE_FILTER_IGNORE
        marker.add_child(inner)
        var name_label := Label.new()
        name_label.text = String(poi.get("name", ""))
        name_label.add_theme_color_override("font_color", Color.WHITE)
        name_label.add_theme_color_override("font_outline_color", Color.BLACK)
        name_label.add_theme_constant_override("outline_size", 3)
        name_label.add_theme_font_size_override("font_size", 9)
        name_label.position = Vector2(-s * 1.5, -s * 1.2)
        name_label.size = Vector2(s * 3, 14)
        name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
        marker.add_child(name_label)
        poi_layer.add_child(marker)


# =====================================================================
#  P0.4: Transit 端点 pin (保留)
# =====================================================================

func render_transit_markers(markers: Array) -> void:
    var pin_layer := Node2D.new()
    pin_layer.name = "TransitPins"
    pin_layer.z_index = 9
    add_child(pin_layer)
    for tm in markers:
        var ex: int = int(tm.get("end_grid_x", -1))
        var ey: int = int(tm.get("end_grid_y", -1))
        if ex < 0 or ey < 0:
            continue
        ex = clamp(ex, 0, grid_w - 1)
        ey = clamp(ey, 0, grid_h - 1)
        var transport: String = String(tm.get("transport", "transit"))
        var color: Color = PALETTE["transit_pin_transit"] if transport == "transit" else PALETTE["transit_pin_driving"]
        var s := float(tile_size)
        var pin := Node2D.new()
        pin.name = "Pin_%s" % String(tm.get("name", ""))
        pin.position = Vector2(ex * s + s * 0.5, ey * s + s * 0.5)
        var head := Polygon2D.new()
        head.color = color
        head.polygon = PackedVector2Array([
            Vector2(0, s * 0.6),
            Vector2(-s * 0.4, -s * 0.2),
            Vector2(s * 0.4, -s * 0.2),
            Vector2(0, -s * 0.4),
        ])
        pin.add_child(head)
        var inner := Polygon2D.new()
        inner.color = Color8(255, 255, 255)
        inner.polygon = PackedVector2Array([
            Vector2(-s * 0.12, -s * 0.1),
            Vector2(s * 0.12, -s * 0.1),
            Vector2(0, s * 0.2),
        ])
        pin.add_child(inner)
        var dist_km: float = float(tm.get("distance_m", 0.0)) / 1000.0
        var dur_min: int = int(float(tm.get("duration_sec", 0.0)) / 60.0)
        var transport_zh: String = "地铁" if transport == "transit" else "开车"
        var label_text: String = "%s %s  %.1fkm / %dmin" % [
            "→", String(tm.get("name", "")), dist_km, dur_min,
        ]
        var label := Label.new()
        label.text = label_text
        label.add_theme_color_override("font_color", Color.WHITE)
        label.add_theme_color_override("font_outline_color", Color.BLACK)
        label.add_theme_constant_override("outline_size", 3)
        label.add_theme_font_size_override("font_size", 10)
        label.position = Vector2(-s * 1.8, -s * 1.5)
        label.size = Vector2(s * 3.6, 14)
        label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
        pin.add_child(label)
        pin_layer.add_child(pin)


# =====================================================================
#  P1.2: 建筑高度渲染 (从 cell 往上抬, levels * 4px)
# =====================================================================

const HEIGHT_PX_PER_LEVEL := 4.0   # 每层 4px 抬高
const SHADOW_ALPHA := 0.45
const ROOF_COLOR := Color8(80, 50, 30)   # 深棕屋顶

func render_buildings_with_height(heights: Array) -> void:
    """遍历 heights, 凡是 height>0 的 cell 画抬高的多边形 + 阴影
    heights: 2D 数组 [[h, ...], ...], 跟 grid 同步大小
    """
    if heights.is_empty():
        return
    var height_layer := Node2D.new()
    height_layer.name = "BuildingHeights"
    height_layer.z_index = 5   # 在 tile 上面, path overlay 下面
    add_child(height_layer)

    var s := float(tile_size)
    var buildings_drawn := 0
    var max_h := 0
    for y in range(grid_h):
        if y >= heights.size():
            break
        var hrow: Array = heights[y]
        for x in range(grid_w):
            if x >= hrow.size():
                break
            var levels: int = int(hrow[x])
            if levels <= 0:
                continue
            var h_px: float = levels * HEIGHT_PX_PER_LEVEL
            var cx: float = x * s + s * 0.5
            var cy: float = y * s + s * 0.5
            # 1) 阴影 (地面投影, 比建筑宽 2px, 浅灰, 半透明)
            var shadow := Polygon2D.new()
            shadow.color = Color8(0, 0, 0, int(255 * SHADOW_ALPHA))
            shadow.polygon = PackedVector2Array([
                Vector2(cx - s * 0.55, cy + s * 0.50 + 2),
                Vector2(cx + s * 0.55, cy + s * 0.50 + 2),
                Vector2(cx + s * 0.65, cy + s * 0.50 + 2 + h_px * 0.3),
                Vector2(cx - s * 0.65, cy + s * 0.50 + 2 + h_px * 0.3),
            ])
            height_layer.add_child(shadow)
            # 2) 建筑侧面 (顶层亮色)
            var side := Polygon2D.new()
            var top_color := Color8(180, 140, 100)   # 顶层亮
            side.color = top_color
            side.polygon = PackedVector2Array([
                # 底面 (在 cell 中心)
                Vector2(cx - s * 0.4, cy + s * 0.3),
                Vector2(cx + s * 0.4, cy + s * 0.3),
                # 顶面 (往上抬 h_px)
                Vector2(cx + s * 0.45, cy + s * 0.3 - h_px),
                Vector2(cx - s * 0.45, cy + s * 0.3 - h_px),
            ])
            height_layer.add_child(side)
            # 3) 屋顶 (横向面, 暗色)
            var roof := Polygon2D.new()
            roof.color = ROOF_COLOR
            roof.polygon = PackedVector2Array([
                Vector2(cx - s * 0.45, cy + s * 0.3 - h_px),
                Vector2(cx + s * 0.45, cy + s * 0.3 - h_px),
                Vector2(cx + s * 0.35, cy + s * 0.3 - h_px - 2),
                Vector2(cx - s * 0.35, cy + s * 0.3 - h_px - 2),
            ])
            height_layer.add_child(roof)
            buildings_drawn += 1
            if levels > max_h:
                max_h = levels
    print("[WorldBuilder] P1.2 building heights: %d buildings drawn, max %d 层" % [buildings_drawn, max_h])


# =====================================================================
#  P1.3: 室内 slot 渲染 (icon + name label)
# =====================================================================

func render_interior_slots(interiors: Array) -> void:
    """画每个 interior slot (用 TileMapLayer 0 + interior source 1)
    interiors: [{name, category, raw_tag, grid_x, grid_y, has_name}, ...]
    设计:
      - icon 画在 building 中心 cell 上
      - 名字 label 写在 icon 旁边 (短名字优先, 没名字跳过 label)
    """
    if interior_set == null:
        push_warning("WorldBuilder: interior_set is null, skip render")
        return
    # 单独的 TileMap (source 1 = interior)
    var interior_tm := TileMap.new()
    interior_tm.name = "InteriorMap"
    interior_tm.tile_set = interior_set
    interior_tm.z_index = 6   # 在 BuildingHeights 上面
    add_child(interior_tm)
    var layer := TileMapLayer.new()
    layer.name = "Layer0"
    interior_tm.add_child(layer)

    # Label 容器
    var label_layer := Node2D.new()
    label_layer.name = "InteriorLabels"
    label_layer.z_index = 7
    add_child(label_layer)

    var drawn := 0
    var skipped := 0
    for slot in interiors:
        var gx: int = int(slot.get("grid_x", -1))
        var gy: int = int(slot.get("grid_y", -1))
        if gx < 0 or gy < 0 or gx >= grid_w or gy >= grid_h:
            skipped += 1
            continue
        var cat: String = String(slot.get("category", ""))
        if not INTERIOR_ATLAS.has(cat):
            skipped += 1
            continue
        var atlas: Vector2i = INTERIOR_ATLAS[cat]
        # source id = 1 (P1.3 interior source)
        layer.set_cell(Vector2i(gx, gy), 1, atlas)
        # 名字 label (有名字才画)
        if slot.get("has_name", false):
            var nm: String = String(slot.get("name", ""))
            if nm != "":
                var lbl := Label.new()
                lbl.text = nm
                lbl.add_theme_color_override("font_color", Color.WHITE)
                lbl.add_theme_color_override("font_outline_color", Color.BLACK)
                lbl.add_theme_constant_override("outline_size", 2)
                lbl.add_theme_font_size_override("font_size", 8)
                lbl.position = Vector2(gx * tile_size - nm.length() * 2, gy * tile_size - 12)
                lbl.size = Vector2(tile_size * 3, 12)
                lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
                label_layer.add_child(lbl)
        drawn += 1
    print("[WorldBuilder] P1.3 interior slots: %d drawn, %d skipped" % [drawn, skipped])
