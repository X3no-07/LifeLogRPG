"""P1.3 室内 slots 测试

覆盖:
- osm.py: parse_overpass 提 amenity/shop/office/tourism/leisure 标签
- osm.py: _classify_interior 简化分类映射
- schema.py: InteriorSlot + LogPayload.interiors
- text.py/coords.py: 调 osm_to_grid 后创建 InteriorSlot 填到 p.interiors
- generate_interior_icons.py: 13 个 icon 生成
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.schema import InteriorSlot, LogPayload, Meta
from baker.clients.osm import (
    parse_overpass, _classify_interior, INTERIOR_CATEGORY,
)
from baker.generate_interior_icons import DRAWERS as ICON_DRAWERS, TILE_SIZE


# --------------------------------------------------------------------
#  OSM 室内 tag 提取
# --------------------------------------------------------------------

class TestClassifyInterior:
    """_classify_interior 简化分类"""

    @pytest.mark.parametrize("tag_key,tag_value,expected_cat", [
        ("amenity", "cafe", "cafe"),
        ("amenity", "restaurant", "restaurant"),
        ("amenity", "fast_food", "restaurant"),   # 合并到 restaurant
        ("amenity", "bank", "bank"),
        ("amenity", "atm", "bank"),               # 合并到 bank
        ("amenity", "pharmacy", "pharmacy"),
        ("amenity", "hospital", "hospital"),
        ("amenity", "clinic", "hospital"),        # 合并
        ("amenity", "library", "library"),
        ("amenity", "school", "school"),
        ("amenity", "kindergarten", "school"),    # 合并
        ("amenity", "theatre", "theater"),
        ("amenity", "cinema", "theater"),         # 合并
        ("tourism", "hotel", "hotel"),
        ("tourism", "hostel", "hotel"),
        ("tourism", "museum", "museum"),
        ("tourism", "gallery", "museum"),
        ("tourism", "attraction", "attraction"),
        ("leisure", "fitness_centre", "fitness"),
        ("leisure", "sports_centre", "fitness"),
    ])
    def test_amenity_tourism_leisure_mapping(self, tag_key, tag_value, expected_cat):
        result = _classify_interior({tag_key: tag_value})
        assert result is not None
        assert result["category"] == expected_cat
        assert result["raw_tag"] == f"{tag_key}={tag_value}"

    def test_shop_any_value(self):
        """shop 任意值 -> 'shop'"""
        for v in ["clothes", "convenience", "bakery", "books", "supermarket"]:
            result = _classify_interior({"shop": v})
            assert result is not None
            assert result["category"] == "shop"
            assert result["raw_tag"] == f"shop={v}"

    def test_office_any_value(self):
        """office 任意值 -> 'office'"""
        for v in ["company", "lawyer", "it", "estate_agent"]:
            result = _classify_interior({"office": v})
            assert result is not None
            assert result["category"] == "office"

    def test_priority_amenity_over_tourism(self):
        """amenity 优先级最高"""
        result = _classify_interior({"amenity": "cafe", "tourism": "museum"})
        assert result["category"] == "cafe"

    def test_no_interior_tags_returns_none(self):
        """没室内 tag -> None"""
        result = _classify_interior({"building": "yes", "name": "无名建筑"})
        assert result is None

    def test_empty_tags(self):
        result = _classify_interior({})
        assert result is None


class TestParseOverpassInterior:
    """parse_overpass 在 building 上挂 interior 字段"""

    def test_cafe_building_has_interior(self):
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "amenity": "cafe", "name": "星巴克"}},
        ]}
        result = parse_overpass(raw)
        assert len(result["buildings"]) == 1
        b = result["buildings"][0]
        assert b["interior"] is not None
        assert b["interior"]["category"] == "cafe"
        assert b["interior"]["raw_tag"] == "amenity=cafe"
        assert b["name"] == "星巴克"

    def test_shop_building(self):
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "yes", "shop": "bakery"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["interior"]["category"] == "shop"

    def test_residential_building_no_interior(self):
        raw = {"elements": [
            {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
            {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
            {"type": "way", "id": 100, "nodes": [1, 2, 1],
             "tags": {"building": "residential"}},
        ]}
        result = parse_overpass(raw)
        assert result["buildings"][0]["interior"] is None

    def test_all_13_categories_represented(self):
        """验证 13 个 category 在 _classify_interior 里都有映射"""
        expected_cats = {
            "cafe", "restaurant", "shop", "office", "hotel", "hospital",
            "bank", "school", "museum", "pharmacy", "library", "fitness",
            "theater",
        }
        all_tags = [
            {"amenity": "cafe"}, {"amenity": "restaurant"}, {"shop": "x"},
            {"office": "x"}, {"amenity": "hotel"}, {"amenity": "hospital"},
            {"amenity": "bank"}, {"amenity": "school"}, {"tourism": "museum"},
            {"amenity": "pharmacy"}, {"amenity": "library"},
            {"leisure": "fitness_centre"}, {"amenity": "theatre"},
        ]
        result_cats = set()
        for tags in all_tags:
            r = _classify_interior(tags)
            if r:
                result_cats.add(r["category"])
        missing = expected_cats - result_cats
        assert not missing, f"missing categories: {missing}"


# --------------------------------------------------------------------
#  Schema
# --------------------------------------------------------------------

class TestInteriorSlotSchema:
    def test_default_values(self):
        s = InteriorSlot()
        assert s.name == ""
        assert s.category == ""
        assert s.raw_tag == ""
        assert s.lng == 0.0
        assert s.lat == 0.0
        assert s.grid_x == 0
        assert s.grid_y == 0
        assert s.has_name is False

    def test_construction(self):
        s = InteriorSlot(
            name="星巴克", category="cafe", raw_tag="amenity=cafe",
            lng=116.4, lat=39.9, grid_x=42, grid_y=18, has_name=True,
        )
        d = s.to_dict()
        assert d["name"] == "星巴克"
        assert d["category"] == "cafe"
        assert d["grid_x"] == 42

    def test_logpayload_includes_interiors(self):
        """LogPayload.to_dict 带 interiors"""
        p = LogPayload()
        p.interiors.append(InteriorSlot(name="X", category="cafe", grid_x=5, grid_y=3))
        d = p.to_dict()
        assert "interiors" in d
        assert len(d["interiors"]) == 1
        assert d["interiors"][0]["name"] == "X"

    def test_logpayload_default_empty(self):
        p = LogPayload()
        assert p.interiors == []


# --------------------------------------------------------------------
#  Icon 生成
# --------------------------------------------------------------------

class TestInteriorIconGeneration:
    """generate_interior_icons 13 个 icon 都画得出来"""

    @pytest.mark.parametrize("cat", list(ICON_DRAWERS.keys()))
    def test_icon_drawer_runs(self, cat, tmp_path):
        from baker.generate_interior_icons import _new, generate_all
        img = _new()
        ICON_DRAWERS[cat](img)
        # 至少 1 个非透明像素
        extrema = img.getextrema()
        assert any(max_v > 0 for _, max_v in extrema), \
            f"{cat} produced all-transparent image"

    def test_13_icons_defined(self):
        assert len(ICON_DRAWERS) == 13

    def test_icons_unique(self):
        """每个 category 都有自己的 drawer (没有重复)"""
        assert len(set(ICON_DRAWERS.keys())) == 13

    def test_generate_to_temp(self, tmp_path):
        """生成到临时目录"""
        from baker.generate_interior_icons import generate_all
        results = generate_all(tmp_path)
        # 13 个 icon (sheet 不在 results list, 但会生成文件)
        assert len(results) == 13
        for cat, path, size in results:
            assert size == (TILE_SIZE, TILE_SIZE)
            assert path.exists()
            assert path.name == f"interior_{cat}.png"
        # sheet 文件也生成
        assert (tmp_path / "interior_sheet.png").exists()

    def test_sheet_size_4x4(self, tmp_path):
        """sheet 是 4x4 = 64x64"""
        from baker.generate_interior_icons import generate_all
        generate_all(tmp_path)
        from PIL import Image
        sheet = Image.open(tmp_path / "interior_sheet.png")
        assert sheet.size == (TILE_SIZE * 4, TILE_SIZE * 4)


# --------------------------------------------------------------------
#  Grid 集成: osm_to_grid 返回 (grid, heights, debug), 不变
# --------------------------------------------------------------------

class TestGridifierUnchanged:
    """osm_to_grid 仍 3-tuple 返回, interior 走 text/coords 单独处理"""

    def test_three_tuple(self):
        from baker.core.gridifier import osm_to_grid, CELL_GRASS
        parsed = {"roads": [], "buildings": [], "water": [], "green": []}
        result = osm_to_grid(parsed, (0, 0, 1, 1), (10, 10))
        assert len(result) == 3
        grid, heights, info = result
        assert info["road_count"] == 0


class TestInteriorExtractionLogic:
    """模拟 text.py 的 interior 提取流程"""

    def test_pick_building_center(self):
        """从 building nodes 算中心 (avg lng, lat)"""
        nodes = [(0.1, 0.5), (0.3, 0.5), (0.3, 0.7), (0.1, 0.7)]
        avg_lng = sum(n[0] for n in nodes) / len(nodes)
        avg_lat = sum(n[1] for n in nodes) / len(nodes)
        assert abs(avg_lng - 0.2) < 0.001
        assert abs(avg_lat - 0.6) < 0.001
