extends Node
class_name WeatherSystem
# WeatherSystem - 天气粒子系统
#
# 支持 4 种天气 (从 meta.weather 字符串读):
#   - sunny:  太阳 (右上角, 黄色圆形, 慢速脉动) + 浅蓝天空
#   - rainy:  雨粒子 (CPUParticles2D) + 暗化 overlay
#   - snowy:  雪粒子 (CPUParticles2D) + 暗化 overlay
#   - cloudy: 云朵 (3 个, 慢速飘) + 暗化 overlay
#   - unknown: 不动
#
# 集成:
#   var weather = WeatherSystem.new()
#   world.add_child(weather)        # 必须 add 到 world, 这样跟随相机滚动
#   weather.setup(world_w, world_h, meta.weather)
#
# 调位置:粒子位置是世界坐标,跟随 player 移动

var tile_size: int = 16
var world_w: int = 80
var world_h: int = 60
var _current: String = "unknown"


func setup(p_world_w: int, p_world_h: int, weather: String) -> void:
    world_w = p_world_w
    world_h = p_world_h
    _current = weather
    match weather:
        "sunny":
            _setup_sunny()
        "rainy":
            _setup_rainy()
        "snowy":
            _setup_snowy()
        "cloudy":
            _setup_cloudy()
        _:
            _current = "unknown"  # unknown: 啥都不做


func get_current() -> String:
    return _current


# =====================================================================
#  Sunny
# =====================================================================

func _setup_sunny() -> void:
    # 太阳 (右上角, 脉动)
    var sun := Node2D.new()
    sun.name = "Sun"
    var s := float(tile_size)
    sun.position = Vector2(world_w * tile_size - s * 3, s * 2)
    var sun_body := ColorRect.new()
    sun_body.color = Color8(255, 220, 100)
    sun_body.size = Vector2(s * 2, s * 2)
    sun_body.position = Vector2(-s, -s)
    sun_body.mouse_filter = Control.MOUSE_FILTER_IGNORE
    sun.add_child(sun_body)
    # 太阳光芒 (4 条)
    for k in 4:
        var ray := ColorRect.new()
        ray.color = Color8(255, 220, 100)
        ray.size = Vector2(s * 0.4, s * 0.8) if k % 2 == 0 else Vector2(s * 0.8, s * 0.4)
        ray.position = Vector2(-s * 0.2, -s * 1.5) if k == 0 else \
                       Vector2(s * 1.0, -s * 0.2) if k == 1 else \
                       Vector2(-s * 0.2, s * 0.7) if k == 2 else \
                       Vector2(-s * 1.5, -s * 0.2)
        ray.mouse_filter = Control.MOUSE_FILTER_IGNORE
        sun.add_child(ray)
    sun.z_index = -10
    add_child(sun)
    # 脉动 tween
    var t := create_tween().set_loops()
    t.tween_property(sun, "modulate:a", 0.7, 1.0)
    t.tween_property(sun, "modulate:a", 1.0, 1.0)
    # 浅蓝天空 overlay (替代默认暗背景)
    _add_overlay(Color8(135, 180, 220, 30), -80)


# =====================================================================
#  Rainy
# =====================================================================

func _setup_rainy() -> void:
    # 雨粒子
    var rain := CPUParticles2D.new()
    rain.name = "Rain"
    rain.amount = 300
    rain.lifetime = 0.6
    rain.preprocess = 0.5
    rain.explosiveness = 0.0
    rain.randomness = 0.3
    rain.direction = Vector2(0.15, 1.0)  # 略微倾斜
    rain.spread = 8.0
    rain.gravity = Vector2(0, 600)
    rain.initial_velocity_min = 500
    rain.initial_velocity_max = 600
    rain.scale_amount_min = 0.8
    rain.scale_amount_max = 1.2
    rain.color = Color8(150, 190, 230, 200)
    rain.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
    var half_w: float = float(world_w) * float(tile_size) / 2.0
    rain.emission_rect_extents = Vector2(half_w, 0.0)
    rain.position = Vector2(half_w, -32)
    rain.z_index = 5
    add_child(rain)

    # 暗化 overlay (乌云)
    _add_overlay(Color(0.05, 0.08, 0.12, 0.30), -50)


# =====================================================================
#  Snowy
# =====================================================================

func _setup_snowy() -> void:
    # 雪粒子
    var snow := CPUParticles2D.new()
    snow.name = "Snow"
    snow.amount = 200
    snow.lifetime = 3.0
    snow.preprocess = 1.0
    snow.explosiveness = 0.0
    snow.randomness = 0.6
    snow.direction = Vector2(0, 1)
    snow.spread = 12.0
    snow.gravity = Vector2(0, 25)
    snow.angular_velocity_min = -30
    snow.angular_velocity_max = 30
    snow.initial_velocity_min = 30
    snow.initial_velocity_max = 50
    snow.scale_amount_min = 1.0
    snow.scale_amount_max = 1.6
    snow.color = Color8(255, 255, 255, 220)
    snow.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
    var half_w: float = float(world_w) * float(tile_size) / 2.0
    snow.emission_rect_extents = Vector2(half_w, 0.0)
    snow.position = Vector2(half_w, -32)
    snow.z_index = 5
    add_child(snow)

    # 暗化 overlay
    _add_overlay(Color(0.10, 0.10, 0.15, 0.20), -50)


# =====================================================================
#  Cloudy
# =====================================================================

func _setup_cloudy() -> void:
    # 3 朵云
    var rng := RandomNumberGenerator.new()
    rng.seed = 42
    for i in range(3):
        var cloud := Node2D.new()
        cloud.name = "Cloud_%d" % i
        var s := float(tile_size)
        # 云 = 3 个椭圆 ColorRect 拼成
        for k in 3:
            var blob := ColorRect.new()
            blob.color = Color8(180, 180, 190, 220)
            blob.size = Vector2(s * 3, s * 1.5) if k == 1 else Vector2(s * 2, s * 1.5)
            blob.position = Vector2(s * (k - 1) * 1.2, 0 if k == 1 else s * 0.4 * (1 if k == 0 else -1))
            blob.mouse_filter = Control.MOUSE_FILTER_IGNORE
            cloud.add_child(blob)
        cloud.position = Vector2(rng.randf() * float(world_w) * float(tile_size),
                                  s * (3 + i * 4))
        cloud.z_index = -10
        add_child(cloud)
        # 飘动 tween (loops)
        var start_x := cloud.position.x
        var t := create_tween().set_loops()
        t.tween_property(cloud, "position:x", start_x + s * 6, 25.0 + float(i) * 4.0)
        t.tween_property(cloud, "position:x", start_x, 25.0 + float(i) * 4.0)
    # 暗化
    _add_overlay(Color(0.20, 0.20, 0.25, 0.15), -50)


# =====================================================================
#  工具
# =====================================================================

func _add_overlay(color: Color, z_index: int) -> void:
    var overlay := ColorRect.new()
    overlay.name = "WeatherOverlay"
    overlay.color = color
    overlay.size = Vector2(float(world_w) * float(tile_size), float(world_h) * float(tile_size))
    overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
    overlay.z_index = z_index
    add_child(overlay)
