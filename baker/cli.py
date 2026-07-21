"""Baker CLI 入口

用法:
  python -m baker.cli --mock
  python -m baker.cli --coords "lng,lat;lng,lat;..."
  python -m baker.cli --text "从家走到地铁, 然后去国贸" --name log_xxx
  python -m baker.cli --text "..." --target-duration 30
"""
import argparse
import sys
from typing import Optional

from . import __version__
from .config import load_config
from .core.time_scale import apply_time_scale
from .modes import MockMode, CoordsMode, TextMode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="baker",
        description=f"Life Log RPG 烘焙脚本 v{__version__}",
    )
    p.add_argument("--mock", action="store_true", help="用 mock 数据生成示例 log (无需 Key)")
    p.add_argument("--coords", type=str, help="经纬度序列, 格式: lng,lat;lng,lat;...")
    p.add_argument("--text", type=str, help="自然语言日志文本 (LLM 解析 + 高德 API)")
    p.add_argument("--name", type=str, default="log_001", help="输出文件名 (不含 .json)")
    p.add_argument("--target-duration", type=float, default=0.0,
                   help="把整个播放压到此秒数 (0=不缩放, 30=朋友圈节奏)")
    p.add_argument("--city", type=str, default="", help="默认城市, 留空用 config 里的 (默认北京)")
    p.add_argument("--verbose", action="store_true", help="详细日志")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config()
    if args.city:
        config.setdefault("bake", {})["default_city"] = args.city

    # 选 mode
    if args.mock:
        mode = MockMode(args.name, config)
    elif args.coords:
        mode = CoordsMode(args.name, args.coords, config)
    elif args.text:
        mode = TextMode(args.name, args.text, config)
    else:
        print("[hint] 未指定模式, 默认用 --mock")
        mode = MockMode(args.name, config)

    payload = mode.run()

    # 后处理: 时间缩放 (直接改 payload 对象, 写到 meta)
    if args.target_duration > 0:
        apply_time_scale(payload, args.target_duration)

    # 写盘
    out_path = mode.write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
