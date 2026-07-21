# Life Log RPG — 像素 RPG 版

> 把你的真实人生日志"烘焙"成 GBA 风格的 2D 像素 RPG 舞台剧,完全离线 0 延迟回放。

## 当前进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| **P0 环境 + 骨架** | ✅ 已完成 | Godot 4.7.1 + 项目骨架 + 烘焙脚本 + 1 份示例 log_001.json |
| **P1 最小 Demo**    | ⏳ 等 API Key | 输入日志 → 高德 API 取真实坐标 → 角色沿真实路径行走 |
| **P2 体感升级**     | 📋 规划中 | 捏脸 / 对话 / 换乘 / 天气 / 音效 |
| **P3 视频导出**     | 📋 规划中 | FFmpeg 录屏 30s / 加密 .dat / UI 打磨 |

## 目录结构

```
F:\LifeLogRPG_Project\
├── project.godot              # Godot 4.7 项目配置
├── config.json                # API Key + 运行参数(无硬编码)
├── README.md                  # 本文件
│
├── tools\godot\godot.exe      # Godot 4.7.1 stable (170 MB, 免安装)
│
├── assets\                    # 静态资源(图标等)
│   └── icon.svg
│
├── scenes\main.tscn           # 主场景 (挂 main.gd)
├── scripts\main.gd            # 主控制器 (413 行 GDScript)
│
├── baker\bake.py              # Python 烘焙脚本 (调高德 + 生成 JSON)
├── saved_logs\log_001.json    # 烘焙输出 (明文 JSON, Demo 阶段)
│
├── data\                      # 占位: 后续放 tileset / sprite
└── exports\                   # 占位: 后续放 30s 视频导出
```

## 启动项目 (P0 已验证可跑)

```powershell
# 1. 启动 Godot 编辑器 (GUI 模式, 手动玩)
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --path "F:\LifeLogRPG_Project"

# 2. 或直接跑当前场景 (会弹窗, 你能看到 80x60 像素地图 + 胶囊人沿路径走)
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --path "F:\LifeLogRPG_Project"

# 3. Headless 验证项目能跑 (无窗口, 60 帧后退出)
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --headless --quit-after 60 --path "F:\LifeLogRPG_Project"
```

## 烘焙新日志

```powershell
cd F:\LifeLogRPG_Project

# 模式 1: Mock 模式 (用预定义路径, 不需要 API Key, 跑通流程)
python baker\bake.py --mock --name log_001

# 模式 2: 坐标模式 (提供经纬度序列)
python baker\bake.py --coords "116.40,39.90;116.41,39.91;116.42,39.92" --name log_002

# 模式 3: 文本模式 (需要高德 Key; P1 阶段启用)
python baker\bake.py --text "我从国贸走到三里屯, 路上碰到老张, 一起去吃了火锅" --name log_003
```

## 运行时操作

| 按键 | 功能 |
|------|------|
| SPACE | 暂停 / 播放 |
| ↑ | 加速 (2x 步进, 最高 8x) |
| ↓ | 减速 (0.5x 步进, 最低 0.25x) |
| R | 重置回起点 |
| 鼠标点进度条 | 跳转播放位置 |

## JSON 数据格式 (log_NNN.json)

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
    "width": 80,
    "height": 60,
    "grid": [[0,0,0,...], ...],   // 0=grass 1=road 2=building 3=water 4=tree
    "legend": {"0":"grass","1":"road","2":"building","3":"water","4":"tree"}
  },
  "path": [
    {"x":5,"y":10,"t":0.0,"label":"home","transport":"walk"},
    {"x":25,"y":10,"t":7.5,"label":"subway","transport":"walk"},
    ...
  ],
  "dialogs": [
    {"t":4.0,"speaker":"Me","text":"出门, 天气不错"},
    {"t":12.0,"speaker":"路人","text":"早! 赶着去上班呢"}
  ],
  "characters": [{"name":"Me","color":"#f2cc2c"}]
}
```

## 下一步 (P1) 需要什么

请提供:
1. **高德地图 Web API Key** — https://lbs.amap.com/dev/key/app 申请 (选 "Web 服务" 类型)
2. **MiniMax API Key** — https://api.minimaxi.com/ 申请 (用 `MiniMax-Text-01` 文本模型, vision 用 `abab6.5s-chat`)

填入 `F:\LifeLogRPG_Project\config.json` 的 `amap.api_key` / `minimax.api_key` 字段后,即可:

```powershell
# P1 端到端跑通
python baker\bake.py --text "我从家走到地铁站, 然后坐地铁去国贸" --name log_002
& "F:\LifeLogRPG_Project\tools\godot\godot.exe" --path "F:\LifeLogRPG_Project" --log=res://saved_logs/log_002.json
```

## 注意事项

- **工作目录**: 严格 F:\LifeLogRPG_Project\, 不写 C 盘
- **JSON 格式**: Demo 阶段明文, 后续 P5 才改 .dat 加密
- **API Key**: 永远从 config.json 读, 源码不硬编码
- **GDScript**: 已用 `@warning_ignore` 抑制严格类型警告 (P0 阶段先跑通, 后续会清理)
