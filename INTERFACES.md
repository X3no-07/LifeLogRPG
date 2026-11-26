# Life Log RPG — 接口与结构规范 (INTERFACES)

> 本文档是 baker ↔ Godot 之间的 **单一事实来源**。
> 任何字段名、模块 API、目录结构变更必须同步更新本文 + `baker/core/schema.py` + `scripts/loader.gd`。

## 0. 项目目录结构

```
LifeLogRPG/
├── project.godot                 # Godot 4.7 项目配置
├── config.json                   # 单一配置中心 (Key + 参数, Key 是占位符)
├── README.md                     # 用户文档
├── HANDOFF.md                    # 给美术的交接文档
├── INTERFACES.md                 # 本文件 (开发接口契约)
│
├── scenes\
│   └── main.tscn                 # 主场景 (挂 scripts\main.gd)
│
├── scripts\                      # Godot 端 (12 个模块)
│   ├── main.gd                   # 主控制器 — 启动 + 主循环
│   ├── loader.gd                 # JSON 加载 + 强校验 (LogLoader)
│   ├── world.gd                  # Tilemap + 路径线 (WorldBuilder)
│   ├── player.gd                 # 角色 sprite 工厂 (Player)
│   ├── transport.gd              # 换乘动画 (TransportSystem)
│   ├── npc.gd                    # NPC 系统 (NpcSystem)
│   ├── ui.gd                     # UI 控件 (UISystem)
│   ├── playback.gd               # 播放控制 (PlaybackController)
│   ├── audio.gd                  # 音效 (AudioSystem)
│   ├── weather.gd                # 天气 (WeatherSystem)
│   ├── avatar_builder.gd         # 捏脸 (AvatarBuilder)
│   └── loading.gd                # 加载场景
│
├── baker\                        # 烘焙脚本 (Python)
│   ├── __init__.py
│   ├── cli.py                    # argparse 入口 (python -m baker.cli)
│   ├── config.py                 # config.json 读取
│   ├── check_api.py              # API 连通性测试 (手动跑)
│   ├── grid_preview.py           # log → PNG 预览
│   ├── vlm_qa.py                 # vision 模型自动检查地图
│   ├── generate_tiles.py         # 生成 8 个地形 tile
│   ├── generate_interior_icons.py # 生成 13 个室内 icon
│   ├── clients\                  # 外部 API 客户端
│   │   ├── amap.py               # 高德 REST (AmapClient)
│   │   ├── llm.py                # LLM (LLMClient, DeepSeek/MiniMax)
│   │   └── osm.py                # OSM Overpass (OsmClient + parse_overpass)
│   ├── modes\                    # 输入模式 (Strategy)
│   │   ├── base.py               # BaseMode
│   │   ├── mock.py               # MockMode (无需 Key)
│   │   ├── coords.py             # CoordsMode (经纬度)
│   │   └── text.py               # TextMode (自然语言, LLM+高德)
│   ├── core\                     # 核心算法
│   │   ├── schema.py             # 数据契约 (LogPayload, Waypoint, Dialog)
│   │   ├── gridifier.py          # 经纬度 -> 网格 + A* 沿路网寻路
│   │   ├── gcj02.py              # GCJ-02 ↔ WGS84 互转
│   │   ├── tiling.py             # 按路径切片 (slice_around_path)
│   │   └── time_scale.py         # 时间缩放
│   └── tests\                    # pytest, 278 个测试
│
├── saved_logs\                   # 烘焙输出 (JSON 文件, Godot 读)
│   └── log_*.json
│
└── exports\                      # 视频导出目标 (P3)
```

Godot 引擎二进制不入库 (`tools/godot/` 已 gitignore)，自己装 Godot 4.7.1。

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

`config.json` 里 `bake.output_dir`，默认 `saved_logs/{name}.json`（相对路径，以项目根目录为准）。

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
  "meta":            { /* Meta */ },
  "map":             { /* MapData */ },
  "path":            [ /* Waypoint, ... */ ],
  "dialogs":         [ /* Dialog, ... */ ],
  "characters":      [ /* Character, ... */ ],
  "pois":            [ /* POI, ... */ ],
  "transit_markers": [ /* TransitMarker, ... */ ],
  "interiors":       [ /* InteriorSlot, ... */ ]
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
| `width` | int | ✓ | `160` | 网格列数 |
| `height` | int | ✓ | `120` | 网格行数 |
| `grid` | int[][] | ✓ | `[]` | `grid[y][x]`, 类型码见下 |
| `building_heights` | int[][] | × | `[]` | 跟 grid 同步, 0=无建筑, N=N 层 (P1.2) |
| `legend` | dict | × | 默认映射 | `{cell_type: name}` (0-4) |
| `legend_extended` | dict | × | 默认映射 | `{cell_type: name}` (5-7) |

**Cell 类型码**:

| 码 | 名称 | 颜色 (GBA 风) |
|----|------|----------------|
| 0 | grass | `#4d8c47` |
| 1 | road | `#6b6b73` |
| 2 | building | `#8c6b4d` |
| 3 | water | `#3366b3` |
| 4 | tree | `#1a6626` |
| 5 | sidewalk | 人行道 |
| 6 | poi | POI 标记 |
| 7 | plaza | 广场/铺装 |

### 2.4 Waypoint

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `x` | int | ✓ | — | 网格列 (0-based) |
| `y` | int | ✓ | — | 网格行 (0-based) |
| `t` | float | ✓ | `0.0` | 时刻 (秒), 已缩放 |
| `label` | string | × | `""` | 地点名 / 路标 |
| `transport` | enum | ✓ | `"walking"` | `walking` / `driving` / `transit` / `bicycling` |

`transport` 是每个点的，同一条路线里可以换：比如开车到宫门口、进宫改步行（见 §9 的 `split_transport_at_gate`）。Godot 端 `player.gd` 按每个点的 `transport` 切 sprite。

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
  "deepseek": { "api_key", "base_url", "text_model", "timeout_sec" },
  "bake":     { "output_dir", "tile_size_px", "viewport_grid_w", "viewport_grid_h", "default_city", "weather_seed", "llm_provider" },
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
| `minimax.text_model` | `MiniMax-M3.1-Flash` |
| `deepseek.base_url` | `https://api.deepseek.com/v1` |
| `deepseek.text_model` | `deepseek-chat` |
| `bake.llm_provider` | `"deepseek"` |
| `minimax.vision_model` | `abab6.5s-chat` |
| `bake.tile_size_px` | `16` |
| `bake.viewport_grid_w` | `160` |
| `bake.viewport_grid_h` | `120` |
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
  ├── baker/core/gcj02.py            # GCJ-02 ↔ WGS84 (text/coords 模式都用)
  ├── baker/core/tiling.py           # slice_around_path
  ├── baker/modes/
  │     ├── base.py ──── core/schema.py
  │     ├── mock.py
  │     ├── coords.py ── core/{gridifier,gcj02,tiling}.py + clients/osm.py
  │     └── text.py ──── clients/{amap,llm,osm}.py + core/{gridifier,gcj02,tiling,time_scale,schema}.py
  └── baker/clients/
        ├── amap.py
        ├── llm.py
        └── osm.py
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

```bash
cd <项目根目录>

# Mock 模式 (无需 Key)
python -m baker.cli --mock --name log_001

# 坐标模式
python -m baker.cli --coords "116.40,39.90;116.41,39.91" --name log_002

# 文本模式 (需要 config.local.json 里有 amap + minimax key)
python -m baker.cli --text "今天从西单走到灵境胡同, 然后坐地铁去西二旗" --name log_003 --target-duration 30
```

### 6.2 启动 Godot

Godot 4.7.1 自己装，引擎二进制不入库。

```bash
# 默认 log (main.gd 里 DEFAULT_LOG_PATH)
godot --path .

# 指定 log
godot --path . --log=res://saved_logs/log_demo.json

# Headless 验证 (无窗口)
godot --headless --quit-after 60 --path . --log=res://saved_logs/log_demo.json
```

### 6.3 API 连通性测试

```bash
python baker/check_api.py
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

5. **P2 清理任务** (已做完):
   - `baker/bake_legacy.py` 已删
   - `baker/debug_amap.py` + `baker/debug_llm.py` 已删
   - `baker/debug_real_*.py` + `baker/debug_way_project.py` + `baker/verify_final.py` 已删 (2026-11-26 清理, 功能被 pytest + check_api 覆盖)

## 8. 已知非核心问题 (P2 阶段处理)

- `config.json` 字段无 JSON Schema 校验 (Pydantic 风格)
- `loader.gd` 用宽松 `.get(key, default)`, schema 校验只 warn 不阻断; 宽/高缺失时 fallback 还是旧的 80×60 (baker 永远写 160×120, 平时碰不到)
- Godot 端无 GUT (Godot Unit Test)
- 视频导出模块未实现 (P3)
- Skeleton2D 真 2D 木偶未实现 (P2.3 捏脸)
- 8-Bit BGM / 天气粒子未实现 (P2.3)

## 9. 路线与坐标 (2026-11-26 烘焙改进)

### 9.1 坐标口径

- 高德给的是 GCJ-02，OSM 是 WGS84，两边差几百米，不能混着用。
- `baker/core/gcj02.py`：`gcj02_to_wgs84` / `wgs84_to_gcj02` / `gcj02_to_wgs84_points`（标准 eviltransform，纯标准库，往返误差约 1.6e-09°）。
- text/coords 模式：高德的点（geocode、路径）先转 WGS84 再切片/投影；问高德要周边 POI 时，切片中心再转回 GCJ-02。OSM 原生的 interiors 不转。
- 天安门一带 GCJ→WGS84 的偏移约 555 米，不转的话路线和路网会对不上。

### 9.2 网格

- 默认 160×120（`config.json` 的 `bake.viewport_grid_w/h`，`baker/core/schema.py` 的 MapData 默认值）。一格多大看切片（自适应切片，半径 800 米、总长约 1.5 公里封顶）；160×120 的格子是竖长方形，320×240 预览版才是一格约 7 米的正方形。
- 楼栅格化用 PIL 多边形填充（`osm_to_grid`），不是逐点 point-in-polygon：320×240 下旧办法要 1 小时，现在不到 1 秒。
- 画的顺序：底（有 ground 数据时默认铺装、否则草地）→ 地面类型 → 绿地 → 水（闭合填面、开放画线宽 2，不再把整条河填成湖）→ 路（画在水上，过河是桥）→ 楼（楼后画，路不再切楼）。
- `building:part` 也算楼（故宫那种大殿碎片），不然大殿会缺块。

### 9.3 路线：A\* 沿路网走

- `baker/core/gridifier.py` 的 `route_along_roads`：锚点先 BFS 吸附到最近的可走格（不限半径），再一段一段 A\* 沿路连起来，最后加密。
- A\* 代价：路/广场/人行道 1，草地 4，树 8；楼/水原则上不走，但有 OSM 路穿过的格（门洞、桥）代价 20，实心楼/水面代价 500（只有实在没路才穿、且走最窄处）。对角线不切楼角。
- 门洞/桥处短暂穿墙的格子由 `carve_route_passages` 刻成路（`apply_path_overlay` 再叠上去）。
- 水边加价：`find_path_on_grid` 的 `water_mask`（`_water_proximity_mask`，水线周围 2 格）让贴水线的可走格 +2.0，路线会走路心/桥心、不贴着水线走。桥本身过河没办法，只能走桥心。
- `densify_and_snap_route` 是老办法（加密 + 局部吸附），没 OSM 数据时 fallback 用它。

### 9.4 主轴吸附 spine_x（库函数，烘焙模式还没接）

- `route_along_roads(..., spine_x=...)`：锚点先横向收到主轴 x（纬度不动），再 BFS 吸附到主轴路上的可走格。主轴位置由调用方从 OSM 数据算（比如午门建筑中心 x），不是写死坐标。
- 用途：老日志的锚点本身偏离主轴（比如天安门那条偏东 30 多格），只靠 BFS 会吸到边路；传了 spine_x 路线就沿主轴走。
- 注意：text/coords 烘焙模式现在还没传 spine_x（见 9.6），故宫那条路线是预览重建脚本调的。

### 9.5 城门分段交通工具 split_transport_at_gate（库函数，烘焙模式还没接）

- `split_transport_at_gate(waypoints, gate_nodes_lnglat, bbox, grid_size, outside="driving", inside="walking")`：城门建筑（OSM 节点）投到网格取包围盒，路线第一次进入包围盒的那一点起步行，之前开车。分段点按 OSM 算，不写死坐标/点号；路线没进包围盒时全段 outside。
- 道理：开车只能到宫门口，进宫城只能步行。
- 注意：text/coords 烘焙模式现在还没调它（见 9.6），故宫那条路线是预览重建脚本调的。

### 9.6 接线状态（实话）

- 烘焙模式（text/coords）已经接了：160×120、GCJ-02 互转、A\* 沿路网、贴水边加价、门洞刻通道。
- 还没接进烘焙模式：`spine_x`、`split_transport_at_gate`。它俩在 `gridifier.py` 里是现成的库函数、有测试，但 text.py/coords.py 没调。想让新烘焙的日志也自动走主轴、进宫自动换步行，得改 text.py/coords.py 接上（这是 baker 逻辑改动，不在这次文档整理里）。
- 预览重建脚本（不在这个仓库，在 `~/workspace/map-preview-firered/`）调了它俩，所以试玩页的故宫路线是沿主轴、进宫步行的。
