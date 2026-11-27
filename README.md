# Life Log RPG

把真实生活日志或经纬度路线做成可回放的俯视像素 RPG 场景。Python Baker 生成地图和回放数据，Godot 负责播放。

## 当前进度

坐标烘焙、真实街景、NPC 对话、换乘、天气、捏脸和回放控制已有原型。最近一版调整了镜头跟随和地图边界。

**下一阶段是美术。** 先做原创四向行走主角和一段王府井实景样片，再统一地图、NPC、交通和界面风格。资产规格、接入位置和验收步骤见 [美术交接方案](HANDOFF.md)。

## 快速体验

安装 Godot 4.7.1，在仓库根目录回放随仓库提供的真实坐标样例。已有存档可直接离线播放。

```powershell
godot --path . --log=res://saved_logs/log_coords_route.json
```

还可以用 `log_p13.json` 回放「从天安门走到故宫」。旧存档只有 JSON 时，播放器会使用 TileMap 绘制。

## 烘焙一段新日志

Python 入口为 `python -m baker.cli`。烘焙需要 Pillow，联网地图与接口调用需要 requests。

```powershell
python -m pip install Pillow requests

# 真实坐标，按项目约定输入 GCJ-02；联网读取 OpenStreetMap
python -m baker.cli --coords "116.40,39.90;116.41,39.91;116.42,39.92" --target-duration 30 --name demo_coords

# 自然语言日记，先配置高德和 DeepSeek 的 Key
python -m baker.cli --text "我从国贸走到三里屯，路上碰到老张，一起去吃了火锅" --name demo_text

# 使用内置模拟数据
python -m baker.cli --mock --name demo_mock
```

坐标模式可通过 OpenStreetMap 的公开接口取得真实街景，并在本地用 A* 寻路。若地图服务取数失败，烘焙器会回退到合成地图。文本模式默认由 DeepSeek 提取地名，并通过高德获取坐标和路径。

生成结果保存在 `saved_logs/`。`<name>.json` 提供回放数据，`<name>_map.png` 提供底图。配置文件可通过 `bake.output_dir` 调整输出位置。默认景物网格为 320×240，每格 16 px，播放器也能读取存档内的其他尺寸。

```powershell
godot --path . --log=res://saved_logs/demo_coords.json
```

实际 API Key 放入 `config.local.json`，也可以用环境变量 `LIFELOG_AMAP_KEY`、`LIFELOG_DEEPSEEK_KEY` 或 `LIFELOG_MINIMAX_KEY`。`python baker/check_api.py` 可以检查接口配置。

## 播放操作

| 操作 | 按键 |
|---|---|
| 暂停和继续 | 空格 |
| 加速或减速 | ↑ / ↓ |
| 从起点重播 | R |
| 跳转 | 点击进度条 |

## 目录与验证

- `baker/` 包含烘焙入口、地图和接口逻辑、像素地图渲染器及测试。
- `scripts/` 和 `scenes/` 包含 Godot 播放器。
- `assets/tiles/` 包含 TileMap、编辑预览和室内图标使用的素材。
- `saved_logs/` 随仓库附带默认回放、实景、换乘、天气和头像示例。新烘焙输出默认留在本机。
- [接口约定](INTERFACES.md) 记录 Baker 与 Godot 之间的数据契约。

```powershell
python -m pip install pytest
python -m pytest baker/tests/
godot --headless --path . --quit-after 60
```
