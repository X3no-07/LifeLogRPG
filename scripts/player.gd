extends Node2D
class_name Player

const PALETTE := {"player": Color8(242, 204, 44), "skin": Color8(242, 191, 140)}
const WALK_ATLAS := "res://assets/characters/urban_walk.png"
const FRAME_SIZE := Vector2i(16, 16)
const WALK_SCALE := 1.5
const DIRECTIONS := ["down", "up", "left", "right"]
const HAIR_VARIANTS := {"spike": 0, "bob": 1, "bald": 2}
const SOURCE_SHIRTS := [[0x42a379, 0x369069], [0xc2504d, 0xa54240], [0xaaa8bd, 0x898ca6]]
const SOURCE_PANTS := [[0xd6d4aa, 0xc5b993], [0xa09cca, 0x7a77a4], [0x60605a, 0x54544e]]
const SOURCE_SKIN := [0xffc999, 0xffc8a1, 0xf1b089, 0xe29779]
const SHIRT_COLORS := {
    "red": [Color("#dc5055"), Color("#ad3847")],
    "blue": [Color("#507bc7"), Color("#345799")],
    "white": [Color("#eeeae4"), Color("#c7c0b6")],
}
const PANTS_COLORS := {
    "blue": [Color("#4d617d"), Color("#34455e")],
    "black": [Color("#4a4650"), Color("#302e35")],
}
const SKIN_COLORS := {
    "light": [Color("#ffe0bd"), Color("#fbd8b1"), Color("#efbe98"), Color("#d69475")],
    "medium": [Color("#f5bd8e"), Color("#efb285"), Color("#d99772"), Color("#b67758")],
    "dark": [Color("#b97654"), Color("#ad6b4d"), Color("#92573f"), Color("#74412e")],
}

static var _source_atlas: Image

var tile_size: int = 16
var _sprites: Dictionary = {}
var _current: String = "walking"
var _walk_sprite: AnimatedSprite2D
var _direction: String = "down"
var _moving: bool = false


func build(p_tile_size: int) -> void:
    tile_size = p_tile_size
    _walk_sprite = AnimatedSprite2D.new()
    _walk_sprite.name = "WalkSprite"
    _walk_sprite.centered = false
    _walk_sprite.offset = Vector2(-FRAME_SIZE.x / 2.0, -FRAME_SIZE.y)
    _walk_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
    _walk_sprite.scale = Vector2.ONE * (WALK_SCALE * tile_size / FRAME_SIZE.x)
    _sprites = {
        "walking": _walk_sprite,
        "driving": _create_drive(),
        "transit": _create_transit(),
        "bicycling": _create_bike(),
    }
    for transport in _sprites:
        var sprite: Node2D = _sprites[transport]
        sprite.visible = transport == _current
        add_child(sprite)
    apply_avatar({})


func apply_avatar(avatar: Dictionary) -> void:
    if _walk_sprite:
        _walk_sprite.sprite_frames = build_avatar_frames(avatar)
        _update_walk_animation()


func set_walk_state(heading: Vector2, moving: bool) -> void:
    if heading.length_squared() > 0.0001:
        if absf(heading.x) > absf(heading.y):
            if _direction in ["left", "right"] or absf(heading.x) > absf(heading.y) * 1.25:
                _direction = "right" if heading.x > 0 else "left"
        else:
            if _direction in ["up", "down"] or absf(heading.y) > absf(heading.x) * 1.25:
                _direction = "down" if heading.y > 0 else "up"
    _moving = moving
    _update_walk_animation()


func switch_to(transport: String) -> bool:
    if transport == _current or not _sprites.has(transport):
        return false
    _sprites[_current].visible = false
    _sprites[transport].visible = true
    _current = transport
    _update_walk_animation()
    return true


func get_current() -> String:
    return _current


func _update_walk_animation() -> void:
    if not _walk_sprite or not _walk_sprite.sprite_frames:
        return
    var is_walking: bool = _moving and _current == "walking"
    var animation := ("walk_" if is_walking else "idle_") + _direction
    var needs_restart := is_walking and not _walk_sprite.is_playing()
    if _walk_sprite.sprite_frames.has_animation(animation) and (_walk_sprite.animation != animation or needs_restart):
        var continuing := is_walking and String(_walk_sprite.animation).begins_with("walk_")
        var previous_frame := _walk_sprite.frame
        var previous_progress := _walk_sprite.frame_progress
        _walk_sprite.play(animation)
        if continuing:
            _walk_sprite.set_frame_and_progress(previous_frame, previous_progress)


static func build_avatar_frames(avatar: Dictionary) -> SpriteFrames:
    var frames := SpriteFrames.new()
    frames.remove_animation("default")
    if _source_atlas == null:
        _source_atlas = _load_walk_atlas()
    if _source_atlas == null:
        return frames

    var variant: int = HAIR_VARIANTS.get(avatar.get("hair", "spike"), 0)
    var origin := Vector2i(0, variant * FRAME_SIZE.y * DIRECTIONS.size())
    var size := Vector2i(FRAME_SIZE.x * 3, FRAME_SIZE.y * DIRECTIONS.size())
    var image := _source_atlas.get_region(Rect2i(origin, size))
    _recolor_avatar(image, variant, avatar)
    if avatar.get("accessory") == "glasses":
        _draw_glasses(image)

    var atlas := ImageTexture.create_from_image(image)
    for direction_index in range(DIRECTIONS.size()):
        var direction: String = DIRECTIONS[direction_index]
        var idle := "idle_" + direction
        var walk := "walk_" + direction
        frames.add_animation(idle)
        frames.set_animation_loop(idle, false)
        frames.add_animation(walk)
        frames.set_animation_speed(walk, 8.0)
        var textures: Array[AtlasTexture] = []
        for frame_index in range(3):
            var frame := AtlasTexture.new()
            frame.atlas = atlas
            frame.region = Rect2(Vector2(FRAME_SIZE * Vector2i(frame_index, direction_index)), Vector2(FRAME_SIZE))
            frame.filter_clip = true
            textures.append(frame)
        frames.add_frame(idle, textures[0])
        for index in [0, 1, 0, 2]:
            frames.add_frame(walk, textures[index])
    return frames


static func _load_walk_atlas() -> Image:
    # Raw PNG supports headless runs before editor import.
    if ResourceLoader.exists(WALK_ATLAS, "Texture2D"):
        var texture := load(WALK_ATLAS) as Texture2D
        if texture:
            return texture.get_image()
    var image := Image.new()
    if image.load_png_from_buffer(FileAccess.get_file_as_bytes(WALK_ATLAS)) == OK:
        return image
    push_error("Player: failed to load " + WALK_ATLAS)
    return null


static func _recolor_avatar(image: Image, variant: int, avatar: Dictionary) -> void:
    var skin: Array = SKIN_COLORS.get(avatar.get("skin"), SKIN_COLORS["medium"])
    var shirt: Array = SHIRT_COLORS.get(avatar.get("shirt"), SHIRT_COLORS["red"])
    var pants: Array = PANTS_COLORS.get(avatar.get("pants"), PANTS_COLORS["blue"])
    var replacements: Dictionary = {}
    for index in range(SOURCE_SKIN.size()):
        replacements[SOURCE_SKIN[index]] = skin[index]
    for index in range(2):
        replacements[SOURCE_SHIRTS[variant][index]] = shirt[index]
        replacements[SOURCE_PANTS[variant][index]] = pants[index]
    for y in range(image.get_height()):
        for x in range(image.get_width()):
            var color := image.get_pixel(x, y)
            var key := color.to_rgba32() >> 8
            if color.a > 0.0 and replacements.has(key):
                image.set_pixel(x, y, replacements[key])


static func _draw_glasses(image: Image) -> void:
    var frame_color := Color("#343044")
    for frame_index in range(3):
        var x := frame_index * FRAME_SIZE.x
        var eye_y := 7 if frame_index == 0 else 6
        image.fill_rect(Rect2i(x + 5, eye_y, 6, 1), frame_color)
        image.fill_rect(Rect2i(x + 4, 2 * FRAME_SIZE.y + eye_y, 3, 1), frame_color)
        image.fill_rect(Rect2i(x + 9, 3 * FRAME_SIZE.y + eye_y, 3, 1), frame_color)


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
