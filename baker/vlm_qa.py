"""P1.4 VLM QA: 烘焙完用 vision model 检查地图合理性

流程:
1. 调 grid_preview 出 PNG (512x384 压缩版)
2. 调 abab6.5s-chat vision, 给 prompt + image
3. 解析 response, 返回 {ok, issues, suggestions}

检查项 (P1.4 MVP):
- 建筑是否贴街道
- 路是否连通
- POI 分布合理
- 整体合理性
- 建筑高度差异 (5 层以上有没有遮挡)
"""
import base64
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests   # 提到顶层, 方便 mock

# QA prompt
QA_PROMPT = """你是一个 GBA 像素 RPG 地图 QA 检查员。这是一张 80x60 网格的真实世界地图截图(从高德 OSM 数据烘焙)。

请检查以下问题, 简洁回答:

1. 建筑是否合理分布? (不能全挤在一块)
2. 道路是否连通? (不能有孤立 cell)
3. POI 标记是否分布合理? (不能全堆在一起)
4. 整体看起来像真实地图吗?

回答格式 (严格 JSON, 第一个字符 {, 最后一个 }):
{
  "ok": true/false,
  "issues": ["问题 1", "问题 2"],
  "suggestions": ["建议 1", "建议 2"],
  "score": 0-100
}

JSON 之外不要任何解释。"""


def _encode_image(path: Path) -> str:
    """图片 -> base64 data URL"""
    import base64
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def render_preview(log_path: Path, out_path: Path) -> Path:
    """调 grid_preview 出一个 PNG 给 vision model 用
    缩放到 512x384 减少 token 数
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grid_preview import render_grid_to_png
    d = json.load(open(log_path, encoding="utf-8-sig"))
    out = render_grid_to_png(
        d["map"]["grid"],
        d.get("path", []),
        pois=d.get("pois", []),
        title="",
        out_path=out_path,
        building_heights=d.get("map", {}).get("building_heights"),
        interiors=d.get("interiors", []),
    )
    return out


def _parse_qa_response(content: str) -> Dict[str, Any]:
    """解析 LLM JSON response, fallback 简单提取"""
    content = content.strip()
    fallback = {"ok": None, "issues": ["parse_fail"], "suggestions": [], "score": None}
    # 策略 1: 直接 json.loads
    try:
        return json.loads(content)
    except Exception:
        pass
    # 策略 2: 去 markdown
    cleaned = content
    if cleaned.startswith("```"):
        import re
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # 策略 3: 正则找 {...}
    import re
    candidates = re.findall(r'\{.*?\}', content, re.DOTALL)
    for cand in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return fallback


def run_qa(log_path: Path, out_dir: Path,
           api_key: str, group_id: str, base_url: str,
           vision_model: str = "abab6.5s-chat") -> Dict[str, Any]:
    """跑一次 VLM QA, 返回 {ok, issues, suggestions, score, raw}
    log_path: saved_logs/log_*.json
    out_dir: PNG 输出目录
    """
    import requests
    # 1) 出 PNG
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{log_path.stem}_qa.png"
    render_preview(log_path, png_path)
    print(f"[vlm_qa] 渲染: {png_path}")

    # 2) 调 vision model
    url = f"{base_url}/text/chatcompletion_v2"
    if group_id:
        url += f"?groupId={group_id}"
    img_url = _encode_image(png_path)
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": vision_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": QA_PROMPT},
                        {"type": "image_url", "image_url": {"url": img_url}},
                    ],
                }],
                "max_tokens": 500,
            },
            timeout=60,
        )
        data = r.json()
        if data.get("base_resp", {}).get("status_code", 0) != 0:
            err = data.get("base_resp", {})
            return {"ok": None, "error": err, "raw": data}
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_qa_response(reply)
        return {"ok": parsed.get("ok"), "issues": parsed.get("issues", []),
                "suggestions": parsed.get("suggestions", []),
                "score": parsed.get("score"), "raw_reply": reply}
    except Exception as e:
        return {"ok": None, "error": str(e)}


if __name__ == "__main__":
    # CLI: python baker/vlm_qa.py <log_path>
    if len(sys.argv) < 2:
        print("usage: python baker/vlm_qa.py <log_path>")
        sys.exit(1)
    log_path = Path(sys.argv[1])
    out_dir = Path(__file__).resolve().parent.parent / "exports" / "qa"
    from config import load_config
    cfg = load_config()
    result = run_qa(
        log_path, out_dir,
        api_key=cfg["minimax"]["api_key"],
        group_id=cfg["minimax"].get("group_id", ""),
        base_url=cfg["minimax"]["base_url"],
        vision_model=cfg["minimax"].get("vision_model", "abab6.5s-chat"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
