# Life Log RPG - 项目 Handoff 文档

> 给做 GBA 美术的 AI 看,1 个文档讲清楚项目全貌 + 需要哪些美术资源

---

## 1. 项目是什么

**Life Log RPG** = 用 GBA 像素 RPG 风格,把用户真实生活日志"还原"成可玩场景的小项目。

- 用户输入一段中文生活日志(比如"从西单走到灵境胡同逛逛,然后坐地铁去西二旗")
- 系统调 LLM 提取地点 → 高德 API 拿真实坐标 + 路径 → OSM 拿真实街网/建筑
- 烘焙成 JSON(160x120 网格地图 + 角色路径 + 室内 slot)
- Godot 4.7.1 加载,角色在 GBA 风格地图上沿街走,2x 缩放,1280x720 窗口
- 30s 一段,像宝可梦那种 top-down RPG 风格

参考: Pokemon GBA / Earthbound / Stardew Valley 那种 16-bit 像素 RPG。

---

## 2. 技术栈

- **baker** (Python 3.14): 烘焙脚本,把日志 → JSON
  - LLM: DeepSeek (`deepseek-chat` 文本，默认；`bake.llm_provider` 可切回 MiniMax `MiniMax-M3.1-Flash` 文本 / `abab6.5s-chat` vision，MiniMax 账号余额不足时 LLM 步骤失败）
  - POI: 高德地图 Web API
  - 地图: OpenStreetMap Overpass API
- **Godot 4.7.1** + GDScript: 运行时,加载 JSON 渲染场景
- **Pillow 12.3.0**: 程序化生成 tile/icon(目前是几何图形,GBA 美术到位后可替换)

---

## 3. 已完成的阶段

| Phase | 状态 | 关键能力 |
|-------|------|----------|
| **P0 环境** | ✅ | Godot 4.7.1 + 项目结构 + baker 框架 |
| **P0.1 OSM 客户端** | ✅ | Overpass QL + 3 备用 URL + User-Agent |
| **P0.2 Slice + Gridify** | ✅ | 矩形切片 (1.5km cap) + Bresenham 画路网 |
| **P0.3 Schema + POI** | ✅ | 完整 JSON schema + 高德 POI 周边 (4 类彩色点) |
| **P0.4 自适应切片** | ✅ | walking 段切片 + transit 端点 pin (clamp 边缘) |
| **P1 End-to-end** | ✅ | text/coords/mock 三模式 + LLM 提取 + 路径 + 对话 |
| **P1.5 时间缩放** | ✅ | `--target-duration 30` 把整段压成 30s |
| **P1.1 真实 Tile** | ✅ | 8 GBA 风格 tile + 运行时 TileSet (PIL 程序化) |
| **P1.2 建筑层数** | ✅ | OSM `building:levels` → 抬高多边形 + 阴影 + 屋顶 |
| **P1.3 室内 Slots** | ✅ | OSM `amenity`/`shop`/`office`/`tourism` → 13 类 icon |
| **P1.4 VLM QA** | ✅ | vision model 自动检查地图合理性 + 打分 |
| **P2.1 Transport** | ✅ | 4 换乘 sprite (walk/drive/transit/bike) + fade 动画 |
| **P2.2 NPC** | ✅ | speaker → 像素方块 + 名字 tag |
| **P2.3 Additions** | ✅ | 278 测试, LoadingScene, AudioSystem, WeatherSystem, AvatarBuilder |
| **2026-11-26 烘焙改进** | ✅ | 网格 160×120 + GCJ-02 对齐 + A* 沿路网寻路 + spine_x 主轴吸附 + 城门分段交通工具 + 水边加价 |
| **P3 视频导出** | 📋 | FFmpeg 录屏 + 30s 输出 + 加密 .dat |

**没做(将来):**
- 真正的 GBA 美术(目前是程序化几何)
- 角色 sprite 行走动画
- 室内场景切换(目前室内 slot 只是 icon)
- 视频导出 P3

---

## 4. 当前 GBA 美术资产情况

**已程序化生成(PIL):**
- 8 个地形 tile: `assets/tiles/{grass,road,building,water,tree,sidewalk,poi,plaza}.png` (16x16, 4x2 sheet)
- 13 个室内 icon: `assets/tiles/interior_{cafe,restaurant,shop,office,hotel,hospital,bank,school,museum,pharmacy,library,fitness,theater}.png` (16x16, 4x4 sheet)

**缺的 (美术需要补的):**

### 4.1 角色 sprite (高优先级)

`scripts/player.gd` 当前用 4 个简单几何 sprite(方块人),需要真正的 GBA 角色:

```
需求: 1 个主角 + 4 个 transport × 4 个方向 × 2-3 帧
主角 base: 16x24 或 16x32 (GBA 标准)
4 transport:
  - walking (走路): 4 方向 × 2 帧 = 8 帧
  - driving (开车): 4 方向 × 1 帧 = 4 帧 (车里看不到,简单)
  - transit (坐地铁): 4 方向 × 1 帧 = 4 帧
  - bicycling (骑车): 4 方向 × 2 帧 = 4 帧 (轮子动)
合计: 20 帧
方向: down/up/left/right (GBA top-down 标准)
```

参考: Pokemon FireRed/LeafGreen 主角,Earthbound Ness (8 帧 walking 循环)

### 4.2 地形 tile 美术 (中优先级)

替换现有程序化 tile,真 GBA 风:

```
8 个 cell type 各自的 16x16 tile:
  0 grass: 草地 (3-4 variants, 不同草丛分布)
  1 road: 道路 (4 variants: 横向/竖向/十字/T 字, + 黄虚线方向感)
  2 building: 建筑屋顶 (3-4 variants, 不同屋顶形状: 坡顶/平顶/瓦片/阁楼)
  3 water: 水面 (2-3 variants, 不同波浪)
  4 tree: 树 (3 variants, 不同树形: 圆顶/尖顶/果树)
  5 sidewalk: 人行道 (2 variants)
  6 plaza: 广场 (2 variants, 不同纹理)
  - poi 不需要单独 tile (POI 是 marker, 已有)
```

参考: Pokemon 地图 tile 集(每个 cell type 4-8 variants 做无缝拼接)

### 4.3 室内 icon 美术 (中优先级)

替换现有 13 个程序化 icon,真 GBA 风:

```
13 个 category 的 16x16 icon:
  cafe, restaurant, shop, office, hotel, hospital, bank
  school, museum, pharmacy, library, fitness, theater

+ 缺的: police (现在 skip 掉)
+ 推荐的: post_office, attraction (目前归在 museum/theater)
```

参考: Pokemon 建筑门口小图标,Stardew Valley 建筑 icon

### 4.4 车辆 / 道具 sprite (低优先级)

```
transit pin 替换: 现在是红/紫色 Polygon2D
  - 地铁 (transit): 火车头小图
  - 开车 (driving): 小车
  - 共享单车 (bicycling): 自行车

NPC: 现在是 speaker 颜色方块
  - 5-6 个 NPC 类型 (老爷爷/上班族/游客/小孩/情侣)
  - 4 方向各 1 帧即可
```

### 4.5 UI 元素 (低优先级)

```
- 对话框边框 (GBA 风带阴影)
- 加载条 (已有 GBA 磁带风)
- 方向键图标 (供 keyboard hint)
- 暂停图标
```

### 4.6 天气 / 特效 (低优先级)

替换 CPUParticles2D 为 sprite:
```
- 雨滴 sprite
- 雪花 sprite
- 落叶 (秋天限定)
- 蒸汽 (咖啡厅烟囱)
```

---

## 5. 风格指南

### 5.1 调色板 (建议用这 16 色 GBA 风)

```
# 基础色
DARK     #2C2C2C  黑/深灰
GRAY     #5C5C5C  灰
LIGHT    #B4B4B4  浅灰
WHITE    #F8F8F8  白
SKY      #264A6B  天空蓝
GRASS    #4D8C47  草绿
WATER    #3366B3  水蓝
ROAD     #6B6B73  路灰
BUILD    #8C6B4D  建筑棕
SAND     #DCC896  沙黄
RED      #B43C3C  红
YELLOW   #DCC850  黄
GREEN    #5A9C50  绿 (POI)
ORANGE   #F46619  橙 (路径)
PURPLE   #C864DC  紫 (POI shop)
PINK     #DC96C8  粉
CYAN     #50B4DC  青 (POI life)
```

### 5.2 像素规则

- **每 tile 16x16 像素** (Godot `TILE_SIZE_PX = 16`)
- **1x1 笔触** (不要抗锯齿,不要 sub-pixel 描边)
- **3-4 色 per tile** (GBA 限制,色彩数不能太多)
- **轮廓 + 1px 阴影** (深色 1px 描边,光源固定从左上)
- **每 sprite 居中** (角色 16x24,锚点在脚下中点)

### 5.3 动画规则

- **走路循环 2 帧**,8 FPS 步频 (GBA 限制)
- **不要超过 4 帧** per action (避免 sprite 数量爆炸)
- **换 transport 0.3s fade** (transport.gd 已实现)
- **不透明度 0.85** 临时遮挡 (transport 切换时)

### 5.4 命名规范

```
assets/sprites/
  player/         (1 个主角)
    walk_down_0.png, walk_down_1.png
    walk_up_0.png, walk_up_1.png
    walk_left_0.png, walk_left_1.png
    walk_right_0.png, walk_right_1.png
    drive_*.png     (4 张)
    transit_*.png   (4 张)
    bike_*.png      (8 张,2 帧轮子动画)

  npc/
    npc_oldman_down.png, npc_business_down.png, ...

  transit_pins/
    pin_train.png, pin_car.png, pin_bike.png

  ui/
    dialog_box.png, pause_icon.png

  weather/
    raindrop.png, snowflake.png
```

PNG 默认 16x16 (角色 16x24 或 16x32),透明背景,索引色或 RGB(A)。

---

## 6. 集成说明

**替换现有资产:**

1. **Tile** - 把 `assets/tiles/*.png` 替换成真 GBA 美术,`generate_tiles.py` 可以保留(留作 fallback 或随机变体生成器)
2. **室内 icon** - 把 `assets/tiles/interior_*.png` 替换成真 GBA 美术
3. **角色 sprite** - 新建 `assets/sprites/player/*.png`,在 `scripts/player.gd` 加 `_load_sprite_animation()` 加载

**Player.gd 集成示例 (待做):**

```gdscript
# 加载 walking 动画
const WALK_DOWN_0 = preload("res://assets/sprites/player/walk_down_0.png")
const WALK_DOWN_1 = preload("res://assets/sprites/player/walk_down_1.png")
# ... 8 个 walking

# 在 _animate() 中:
if moving and facing == "down":
    sprite.texture = WALK_DOWN_0 if (frame % 16 < 8) else WALK_DOWN_1
```

**关键文件位置:**

- 角色: `scripts/player.gd` (685 行,大头是 AvatarBuilder)
- 地形: `scripts/world.gd` (用 TileMap + TileSet,已 runtime 加载 PNG)
- 室内: `scripts/world.gd` render_interior_slots() (类似 TileMap)
- NPC: `scripts/npc.gd` (目前是 placeholder)
- 天气: `scripts/weather.gd` (用 CPUParticles2D,可改 Sprite2D)

---

## 7. 优先级建议

如果你时间有限,按这个顺序做,影响最大:

| 优先级 | 资产 | 工作量 | 影响 |
|--------|------|--------|------|
| 🥇 P0 | 主角 walking 4 方向 × 2 帧 = **8 张** | 0.5 天 | 核心 - 现在方块人太丑 |
| 🥇 P0 | 主角 3 个 transport sprite (drive/transit/bike 各 4 方向) = **12 张** | 0.5 天 | 换乘是核心玩法 |
| 🥈 P1 | 8 个 tile × 2-3 variants = **20 张** | 1 天 | 地图好看 80% 靠 tile |
| 🥈 P1 | 13 个室内 icon = **13 张** | 0.5 天 | 地图细节 |
| 🥉 P2 | 5-6 个 NPC sprite = **6 张** | 0.3 天 | 角色多样性 |
| 🥉 P2 | Transit pin + 天气 sprite = **5 张** | 0.2 天 | 视觉点缀 |
| ⏳ P3 | UI 元素 = **3-5 张** | 0.2 天 | 锦上添花 |

**最小可玩版本(必须):** P0 角色 20 张 + P1 地形 20 张 = **40 张**
**完整版:** + 室内 13 + NPC 6 + 装饰 5 = **64 张**

---

## 8. 验证方法

美术资产到位后,在 Godot 里跑 (Godot 4.7.1 自己装,引擎二进制不入库):

```bash
LIFELOG_JSON="res://saved_logs/log_p13.json" godot --path .
```

应该看到:
- 主角有真正的 sprite (替代方块人)
- 地图是 GBA 像素风 (替代程序化 tile)
- 室内 icon 是艺术风 (替代几何 icon)
- 走到 building cell 触发 transport 切换时,sprite 平滑切换

预览用 `baker/grid_preview.py`:

```bash
python baker/grid_preview.py --log saved_logs/log_p13.json --out exports/check.png
```

---

## 9. 参考资源

**参考游戏 sprite 集 (公开 / 自由使用):**
- Pokemon FireRed/LeafGreen decompilation (`pret/pokeemerald`)
- Stardew Valley 资源
- OpenGameArt.org (搜 "16x16 RPG" 或 "GBA tileset")

**风格参考:**
- Earthbound / Mother 2 (温馨 16-bit 风)
- Stardew Valley (现代像素 RPG)
- Pokemon GBA (top-down RPG 金标准)

**工具建议:**
- Aseprite (付费, 最专业)
- LibreSprite (免费, Aseprite fork)
- Piskel (在线免费)
- Pyxel Edit (付费, 像素 art 专用)

---

## 10. 联系方式 (项目位置)

- **项目根目录:** 本仓库根目录 (PC 上一般是 `F:\LifeLogRPG_Project\`)
- **关键文件:**
  - `baker/` Python 烘焙脚本
  - `scripts/` Godot GDScript
  - `assets/tiles/` 当前程序化 tile
  - `saved_logs/*.json` 已有烘焙好的 log (天安门/西单 等)
  - `exports/qa/` VLM QA 输出

有什么不清楚的,看代码或问做后端那个 AI (他熟)。
