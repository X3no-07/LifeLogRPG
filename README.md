# Life Log RPG — 像素 RPG 版

> 把你的真实人生日志"烘焙"成 GBA 风格的 2D 像素 RPG 舞台剧，完全离线 0 延迟回放。

## 当前进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| **P0 环境 + 骨架** | ✅ 已完成 | Godot 4.7.1 + 项目骨架 + 烘焙脚本 + 示例 log |
| **P1 最小 Demo** | ✅ 已完成 | 文本/坐标/mock 三模式 + LLM 提取地点 + 高德路径 + OSM 地图 + 对话 |
| **P2 体感升级** | ✅ 已完成 | 换乘 sprite + NPC + 天气 + 音效 + 捏脸 + 加载场景 |
| **2026-11-26 烘焙改进** | ✅ 已完成 | 网格 160×120、GCJ-02 对齐、A\* 沿路网寻路、主轴吸附、城门分段交通工具、水边加价 |
| **P3 视频导出** | 📋 规划中 | FFmpeg 录屏 30s / 加密 .dat / UI 打磨 |

## 目录结构

```
LifeLogRPG/
├── project.godot              # Godot 4.7 项目配置
├── config.json                # 配置（Key 是占位符，真 Key 放 config.local.json）
├── README.md                  # 本文件
├── HANDOFF.md                 # 给美术的交接文档
├── INTERFACES.md              # baker ↔ Godot 的接口契约（单一事实来源）
├── scenes/main.tscn           # 主场景
├── scripts/                   # Godot 端（main/loader/world/player/transport/npc/ui/playback/audio/weather/avatar_builder/loading）
├── baker/                     # Python 烘焙包
│   ├── cli.py                 # 入口：python -m baker.cli
│   ├── config.py              # 读 config.json
│   ├── check_api.py           # 测高德 / MiniMax 的 Key 能不能用
│   ├── grid_preview.py        # 把烘焙好的 log 渲染成 PNG 预览
│   ├── vlm_qa.py              # vision 模型自动检查地图合理性
│   ├── generate_tiles.py      # 生成 8 个地形 tile（程序化）
│   ├── generate_interior_icons.py  # 生成 13 个室内 icon（程序化）
│   ├── clients/               # 高德 / MiniMax / OSM 三个客户端
│   ├── core/                  # schema / gridifier（栅格化 + 寻路）/ gcj02 / tiling / time_scale
│   ├── modes/                 # mock / coords / text 三种输入模式
│   └── tests/                 # pytest，278 个测试
├── assets/tiles/              # 程序化生成的 tile 和室内 icon（PNG）
├── saved_logs/                # 烘焙输出（JSON，Godot 直接读）
├── data/ exports/             # 占位目录
```

## 跑起来

### 烘焙（Python，不用 Key 也能跑 mock）

```bash
# mock 模式：预定义数据，不需要任何 Key
python -m baker.cli --mock --name log_001

# 坐标模式：给经纬度序列
python -m baker.cli --coords "116.40,39.90;116.41,39.91;116.42,39.92" --name log_002

# 文本模式：需要 config.local.json 里有高德 + MiniMax Key
python -m baker.cli --text "我从国贸走到三里屯，路上碰到老张，一起去吃了火锅" --name log_003
```

输出写到 `saved_logs/{name}.json`（`config.json` 里 `bake.output_dir` 可改，相对路径以项目根目录为准）。

### 跑 Godot

Godot 4.7.1 需要自己装，引擎二进制不入库（`tools/godot/` 已 gitignore）。装好后：

```bash
# 编辑器里打开项目玩
godot --path .

# 指定一个 log 跑
godot --path . --log=res://saved_logs/log_p13.json

# 也可以用环境变量指定 log
LIFELOG_JSON=res://saved_logs/log_p13.json godot --path .

# 无窗口验证（60 帧后退出）
godot --headless --quit-after 60 --path .
```

## 运行时操作

| 按键 | 功能 |
|------|------|
| SPACE | 暂停 / 播放 |
| ↑ | 加速（2x 步进，最高 8x） |
| ↓ | 减速（0.5x 步进，最低 0.25x） |
| R | 重置回起点 |
| 鼠标点进度条 | 跳转播放位置 |

## 烘焙出来的 JSON 长什么样（saved_logs/log_*.json）

顶层 8 个字段：`meta` / `map` / `path` / `dialogs` / `characters` / `pois` / `transit_markers` / `interiors`。详细契约看 INTERFACES.md，这里只列个样子：

```json
{
  "meta": {
    "log_id": "log_001",
    "title": "Mock 日志 - 城市漫游",
    "created_at": "2026-07-21 20:54",
    "weather": "sunny",
    "mood": "happy",
    "bgm": "town.mid"
  },
  "map": {
    "tile_size": 16,
    "width": 160,
    "height": 120,
    "grid": [[0,0,0,...], ...],
    "legend": {"0":"grass","1":"road","2":"building","3":"water","4":"tree","5":"sidewalk","6":"poi","7":"plaza"}
  },
  "path": [
    {"x":5,"y":10,"t":0.0,"label":"step_0","transport":"walking"},
    {"x":25,"y":10,"t":7.5,"label":"step_5","transport":"transit"},
    ...
  ],
  "dialogs": [
    {"t":4.0,"speaker":"Me","text":"出门，天气不错"},
    {"t":12.0,"speaker":"路人","text":"早！赶着去上班呢"}
  ],
  "characters": [{"name":"Me","color":"#f2cc2c"}]
}
```

- 地图是 160×120 格，一格 16 像素。格子类型：0 草地、1 路、2 建筑、3 水、4 树、5 人行道、6 POI 标记、7 广场。
- 路径上每一点都有 `transport`（walking/driving/transit/bicycling），同一条路线里可以换交通工具（比如开车到宫门口、进宫改步行）。
- 路线是沿真实路网走的（A\* 寻路），不是两点直线。

## 烘焙是怎么跑的（简版）

1. 文本模式：MiniMax 从日志里提取地点 → 高德 geocode 拿坐标（GCJ-02）→ 转成 WGS84 对齐 OSM → 高德拿路径 → 按路径切一块 160×120 的地图 → OSM 拉路网/建筑/水/绿地 → 栅格化 → A\* 沿路网把路线连起来 → 高德拉周边 POI → 生成对话。
2. 坐标模式：直接给经纬度，跳过 LLM 和 geocode，后面一样。
3. mock 模式：预定义数据，什么 Key 都不要。

坐标口径：高德给的是 GCJ-02，OSM 是 WGS84。baker 在 `baker/core/gcj02.py` 里转：高德的点先转 WGS84 再切片/投影；问高德要周边 POI 时，切片中心再转回 GCJ-02。两边不要混。

## 还没做

- 真正的 GBA 美术（现在 tile/icon 都是程序生成的几何图形）
- 角色行走动画（现在是方块人/简单 sprite）
- 室内场景切换（室内 slot 现在只是 icon）
- P3 视频导出（FFmpeg 录屏 + 加密 .dat）

## 注意事项

- **API Key**：永远从 `config.local.json`（gitignored）或环境变量 `LIFELOG_AMAP_KEY` / `LIFELOG_MINIMAX_KEY` 读，源码和 `config.json` 里不放真 Key。`config.json` 里的 Key 是占位符。
- **测试**：`baker/tests/` 里 278 个 pytest 测试，跑 `python -m pytest baker/tests/`。
- **API 连通性**：`python baker/check_api.py` 测高德和 MiniMax 的 Key 能不能用。
- **改接口的规矩**：字段名、模块 API、目录结构变了，要同步改 `baker/core/schema.py` + `scripts/loader.gd` + `INTERFACES.md`，三处对得上。
