# Life Log RPG — 接口与结构规范 (INTERFACES)

> 本文档是 baker ↔ Godot 之间的 **单一事实来源**。
> 任何字段名、模块 API、目录结构变更必须同步更新本文 + `baker/core/schema.py` + `scripts/loader.gd`。

## 0. 项目目录结构

```
F:\LifeLogRPG_Project\
├── project.godot                 # Godot 4.7 项目配置
├── config.json                   # 单一配置中心 (Key + 参数)
├── README.md                     # 用户文档
├── INTERFACES.md                 # 本文件 (开发接口契约)
│
├── scenes\
│   └── main.tscn                 # 主场景 (挂 scripts\main.gd)
│
├── scripts\                      # Godot 端 (7 个模块, 每个 < 200 行)
│   ├── main.gd                   # 主控制器 (~280 行) — 启动 + 主循环
│   ├── loader.gd                 # JSON 加载 + 强校验 (LogLoader)
│   ├── world.gd                  # Tilemap + 路径线 (WorldBuilder)
│   ├── player.gd                 # 角色 sprite 工厂 (Player)
│   ├── transport.gd             # 换乘动画 (TransportSystem)
│   ├── npc.gd                    # NPC 系统 (NpcSystem)
│   ├── ui.gd                     # UI 控件 (UISystem)
│   └── playback.gd               # 播放控制 (PlaybackController)
│
├── baker\                        # 烘焙脚本 (Python, 8 个模块)
│   ├── __init__.py
│   ├── cli.py                    # argparse 入口
│   ├── config.py                 # config.json 读取
│   ├── clients\                  # 外部 API 客户端
│   │   ├── amap.py               # 高德 REST (AmapClient)
│   │   └── llm.py                # MiniMax (LLMClient)
│   ├── modes\                    # 输入模式 (Strategy)
│   │   ├── base.py               # BaseMode
│   │   ├── mock.py               # MockMode (无需 Key)
│   │   ├── coords.py             # CoordsMode (经纬度)
│   │   └── text.py               # TextMode (自然语言, LLM+高德)
│   ├── core\                     # 核心算法
│   │   ├── schema.py             # 数据契约 (LogPayload, Waypoint, Dialog)
│   │   ├── gridifier.py          # 经纬度 -> 网格
│   │   └── time_scale.py         # 时间缩放
│   ├── out\                      # 临时输出 (空)
│   ├── tests\                    # pytest (TODO)
│   ├── bake_legacy.py            # 重构前的单文件 (P2 阶段)
│   ├── test_api.py               # API 连通性测试
│   └── debug_*.py                # 临时 debug (P2 阶段删)
│
├── saved_logs\                   # 烘焙输出 (JSON 文件, Godot 读)
│   └── log_*.json
│
├── tools\godot\godot.exe         # Godot 4.7.1 stable (免安装)
└── exports\                      # 视频导出目标 (P3)
```

## 1. Baker CLI 接口

### 1.1 命令

```bash
python -m baker.cli [OPTIONS]
```

### 1.2 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `--mock` | flag | 用预定义数据, 不需要任何 API Key |
| `--coords` | string | 经纬度序列 `"lng,lat;lng,lat;..."` |
| `--text` | string | 自然语言日志文本 |
| `--name` | string | 输出文件名 (默认 `log_001`, 不含 `.json`) |
| `--target-duration` | float | 把整个播放压到此秒数 (0=不缩放, 30=朋友圈节奏) |
| `--city` | string | POI 搜索默认城市 (默认 `北京`, 留空用 config) |
| `--verbose` | flag | 详细日志 |
| `--version` | flag | 输出版本 |

### 1.3 三选一输入

`--mock` / `--coords` / `--text` 必须且只能选一个;不指定默认 `--mock`。

### 1.4 输出位置

`config.json` 里 `bake.output_dir`,默认 `F:\LifeLogRPG_Project\saved_logs\{name}.json`。

### 1.5 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 地点数 < 2 |
| 3 | 高德 Key 缺失 |
| 4 | geocode 成功数 < 2 |
| 5 | 无有效路径点 |

## 2. JSON 数据契约 (saved_logs/log_*.json)

> 这是 baker 写 / Godot 读的核心接口。
> Python 端定义: `baker/core/schema.py` (dataclass)
> Godot 端解析: `scripts/loader.gd` (LogLoader)
> 任何字段变更必须三处同步。

### 2.1 顶层结构

```json
{
  "meta":       { /* Meta */ },
  "map":        { /* MapData */ },
  "path":       [ /* Waypoint, ... */ ],
  "dialogs":    [ /* Dialog, ... */ ],
  "characters": [ /* Character, ... */ ]
}
```

### 2.2 Meta

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `log_id` | string | ✓ | `""` | 通常等于 filename |
| `title` | string | ✓ | `""` | UI 顶部显示 |
| `created_at` | string | ✓ | `""` | ISO 8601 (`2026-07-21 23:00:00`) |
| `weather` | enum | ✓ | `"unknown"` | `sunny`/`rainy`/`cloudy`/`snowy`/`unknown` |
| `mood` | enum | ✓ | `"calm"` | `happy`/`calm`/`sad`/`excited`/`tired` |
| `bgm` | string | × | `""` | 8-bit 音乐标识 (`town01.mid`) — P2.3 |
| `original_duration_sec` | float | × | `0.0` | P1.5: 缩放前的真实时长 |
| `scaled_duration_sec` | float | × | `0.0` | P1.5: 缩放后的播放时长 |
| `raw_text` | string | × | `""` | debug 用, 原始日志 |

### 2.3 MapData

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `tile_size` | int | ✓ | `16` | 每格像素 |
| `width` | int | ✓ | `80` | 网格列数 |
| `height` | int | ✓ | `60` | 网格行数 |
| `grid` | int[][] | ✓ | `[]` | `grid[y][x]`, 类型码见下 |
| `legend` | dict | × | 默认映射 | `{cell_type: name}` |

**Cell 类型码** (P0 阶段):

| 码 | 名称 | 颜色 (GBA 风) |
|----|------|----------------|
| 0 | grass | `#4d8c47` |
| 1 | road | `#6b6b73` |
| 2 | building | `#8c6b4d` |
| 3 | water | `#3366b3` |
| 4 | tree | `#1a6626` |

### 2.4 Waypoint

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `x` | int | ✓ | — | 网格列 (0-based) |
| `y` | int | ✓ | — | 网格行 (0-based) |
| `t` | float | ✓ | `0.0` | 时刻 (秒), 已缩放 |
| `label` | string | × | `""` | 地点名 / 路标 |
| `transport` | enum | ✓ | `"walking"` | `walking` / `driving` / `transit` / `bicycling` |

### 2.5 Dialog

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `t` | float | ✓ | `0.0` | 时刻 (秒), 已缩放 |
| `speaker` | string | ✓ | `"Me"` | `Me` / `老张` / `同事` / `路人` / ... |
| `text` | string | ✓ | `""` | 中文 5-30 字 |

### 2.6 Character (预留, P2 阶段用)

| 字段 | 类型 | 默认 |
|------|------|------|
| `name` | string | `"Me"` |
| `color` | string (hex) | `"#f2cc2c"` |
| `sprite` | string | `""` (P2.3 捏脸) |

## 3. config.json 接口

> 单一配置中心, **不硬编码在源码**。

### 3.1 结构

```json
{
  "amap":     { "api_key", "base_url", "timeout_sec" },
  "minimax":  { "api_key", "group_id", "base_url", "text_model", "vision_model", "timeout_sec" },
  "bake":     { "output_dir", "tile_size_px", "viewport_grid_w", "viewport_grid_h", "default_city", "weather_seed" },
  "playback": { "default_speed", "min_speed", "max_speed" },
  "export":   { "video_default_duration_sec", "video_fps", "video_resolution", "ffmpeg_path" }
}
```

### 3.2 默认值 (config 缺失时)

| 字段 | 默认 |
|------|------|
| `amap.api_key` | `""` |
| `amap.base_url` | `https://restapi.amap.com/v3` |
| `minimax.base_url` | `https://api.minimaxi.com/v1` |
| `minimax.text_model` | `MiniMax-Text-01` |
| `minimax.vision_model` | `abab6.5s-chat` |
| `bake.tile_size_px` | `16` |
| `bake.viewport_grid_w` | `80` |
| `bake.viewport_grid_h` | `60` |
| `bake.default_city` | `"北京"` |
| `playback.default_speed` | `1.0` |
| `playback.min_speed` | `0.25` |
| `playback.max_speed` | `8.0` |

## 4. Godot 模块 API

> 所有模块通过 `class_name` 全局注册。模块间通信用 signal + 共享引用。

### 4.1 模块清单

| 类 | 文件 | 基类 | 职责 |
|----|------|------|------|
| `LogLoader` | `scripts/loader.gd` | `RefCounted` | JSON 加载 + 强校验 |
| `WorldBuilder` | `scripts/world.gd` | `Node2D` | 地图 + 路径线 |
| `Player` | `scripts/player.gd` | `Node2D` | 角色 + 4 种 transport sprite |
| `TransportSystem` | `scripts/transport.gd` | `Node` | 换乘动画 |
| `NpcSystem` | `scripts/npc.gd` | `Node` | NPC 显示 |
| `UISystem` | `scripts/ui.gd` | `Node` | UI 控件 |
| `PlaybackController` | `scripts/playback.gd` | `Node` | 时间 / 暂停 / 倍速 |

### 4.2 LogLoader 公开 API

```gdscript
var loader: LogLoader
loader.load(path: String) -> Dictionary
loader.get_waypoints() -> Array
loader.get_dialogs() -> Array
loader.get_map() -> Dictionary
loader.get_log_meta() -> Dictionary       # 注意: 不叫 get_meta (跟 Node 冲突)
loader.get_tile_size() -> int
loader.get_grid_width() -> int
loader.get_grid_height() -> int
loader.get_grid() -> Array
loader.get_total_duration() -> float
loader.get_log_title() -> String
```

### 4.3 Player 公开 API

```gdscript
var player: Player
player.build(tile_size: int) -> void
player.switch_to(transport: String) -> bool    # 返回是否真的切换了
player.get_current() -> String                  # walking/driving/transit/bicycling
player.get_eye_node() -> Node                   # 朝向指示点
```

### 4.4 TransportSystem 公开 API

```gdscript
var ts: TransportSystem
ts.setup(ui_layer: CanvasLayer, player: Player) -> void
ts.request_switch(from: String, to: String) -> void     # 触发换乘动画
ts.is_in_transition() -> bool
ts.get_current() -> String
ts.sync_current(transport: String) -> void              # 初始化时用, 无动画
```

### 4.5 NpcSystem 公开 API

```gdscript
var npc: NpcSystem
npc.setup(npc_layer: Node2D, tile_size: int) -> void
npc.update(current_time: float, dialogs: Array, player_pos: Vector2) -> void
```

### 4.6 UISystem 公开 API

```gdscript
var ui: UISystem
ui.setup(parent: Node) -> void
ui.update_progress(current_time: float, total_duration: float) -> void
ui.update_speed(is_playing: bool, speed: float, current_time: float, total_duration: float) -> void
ui.update_status(title: String, mood: String) -> void
ui.update_dialog(speaker: String, text: String) -> void
ui.reset_dialog() -> void
# 公开节点:
ui.progress_bar: ProgressBar
ui.speed_label: Label
ui.status_label: Label
ui.dialog_label: Label
ui.ui_layer: CanvasLayer
```

### 4.7 PlaybackController 公开 API

```gdscript
var pb: PlaybackController
pb.setup(total: float, min_speed: float, max_speed: float, default: float) -> void
pb.start() / pause() / toggle() / reset() / seek_to(t: float)
pb.set_speed(s: float) / bump_speed_up() / bump_speed_down()
pb.update(delta: float) -> void
pb.is_finished() -> bool
# signal:
pb.time_changed(current_time: float)
```

### 4.8 WorldBuilder 公开 API

```gdscript
var world: WorldBuilder
world.build(loader: LogLoader) -> void
# 公开节点 (供其他模块 add_child):
world.tilemap: Node2D
world.path_overlay: Node2D
world.npc_layer: Node2D
```

## 5. 模块依赖图

```
baker/cli.py
  ├── baker/config.py
  ├── baker/core/time_scale.py
  │     └── baker/core/schema.py
  ├── baker/modes/
  │     ├── base.py ──── core/schema.py
  │     ├── mock.py
  │     ├── coords.py ── core/gridifier.py
  │     └── text.py ──── clients/{amap,llm}.py + core/{gridifier,time_scale,schema}.py
  └── baker/clients/
        ├── amap.py
        └── llm.py
```

```
Godot main.tscn
  └── scripts/main.gd
        ├── LogLoader (loader.gd)
        ├── WorldBuilder (world.gd)
        ├── Player (player.gd)
        ├── TransportSystem (transport.gd)
        │     └── Player
        ├── NpcSystem (npc.gd)
        ├── UISystem (ui.gd)
        └── PlaybackController (playback.gd)
              └── signal time_changed -> main._on_time_changed
```

跨进程数据流: `baker/cli.py → saved_logs/log_*.json → Godot LogLoader.load() → 各模块`。

## 6. 启动 / 运行命令 (P0~P2.2)

### 6.1 烘焙新日志

```powershell
cd F:\LifeLogRPG_Project
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 | Out-Null

# Mock 模式 (无需 Key)
python -m baker.cli --mock --name log_001

# 坐标模式
python -m baker.cli --coords "116.40,39.90;116.41,39.91" --name log_002

# 文本模式 (需要 config.json 里有 amap + minimax key)
python -m baker.cli --text "今天从西单走到灵境胡同, 然后坐地铁去西二旗" --name log_003 --target-duration 30
```

### 6.2 启动 Godot

```powershell
# 默认 log (config 里 DEFAULT_LOG_PATH)
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --path "F:\LifeLogRPG_Project"

# 指定 log
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --path "F:\LifeLogRPG_Project" --log=res://saved_logs/log_demo.json

# Headless 验证 (无窗口)
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --headless --quit-after 60 --path "F:\LifeLogRPG_Project" --log=res://saved_logs/log_demo.json
```

### 6.3 API 连通性测试

```powershell
python F:\LifeLogRPG_Project\baker\test_api.py
```

## 7. 维护规范 (新增功能时)

1. **改字段名**:
   - Python 端: `baker/core/schema.py` dataclass
   - Godot 端: `scripts/loader.gd` `_validate()`
   - 文档: 本文件 §2

2. **加新 mode**:
   - `baker/modes/your_mode.py`,继承 `BaseMode`,实现 `run() -> LogPayload`
   - 在 `baker/modes/__init__.py` 注册
   - 在 `baker/cli.py` `build_parser()` 加 argparse 参数
   - 在 `build_parser()` `main()` 加分支

3. **加新 Godot 模块**:
   - `scripts/your_module.gd`,首行 `class_name YourModule extends X`
   - 写文档: 本文件 §4 加新 API
   - 在 `scripts/main.gd` `_build_modules()` 注册

4. **加测试**:
   - `baker/tests/test_xxx.py`, pytest 风格
   - 跑 `python -m pytest baker/tests/`

5. **P2 清理任务**:
   - 删 `baker/bake_legacy.py`
   - 删 `baker/debug_amap.py` + `baker/debug_llm.py`
   - 移到 `baker/tests/` 改成正式测试

## 8. 已知非核心问题 (P2 阶段处理)

- `config.json` 字段无 JSON Schema 校验 (Pydantic 风格)
- `loader.gd` 用宽松 `.get(key, default)`, schema 校验只 warn 不阻断
- baker 无 pytest,Godot 端无 GUT (Godot Unit Test)
- 视频导出模块未实现 (P3)
- Skeleton2D 真 2D 木偶未实现 (P2.3 捏脸)
- 8-Bit BGM / 天气粒子未实现 (P2.3)
