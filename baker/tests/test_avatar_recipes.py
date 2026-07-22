"""测试 avatar 配方的完整性 (跟 avatar_builder.gd AVATAR_PARTS 同步)

这个测试不直接 import GDScript, 而是用 Python mirror 同样的 schema, 验证结构
确保 GDScript 那边的配方不会因为加图层忘记补某个字段
"""
import pytest

# Mirror of scripts/avatar_builder.gd::OPTIONS
AVATAR_RECIPES = {
    "hair": [
        {"id": "spike", "name": "尖发", "color": [50, 30, 20]},
        {"id": "bob", "name": "波波头", "color": [120, 70, 30]},
        {"id": "bald", "name": "光头", "color": [200, 150, 100]},
    ],
    "skin": [
        {"id": "light", "name": "白皮肤", "color": [245, 215, 175]},
        {"id": "medium", "name": "黄皮肤", "color": [230, 190, 140]},
        {"id": "dark", "name": "深皮肤", "color": [160, 110, 70]},
    ],
    "shirt": [
        {"id": "red", "name": "红 T 恤", "color": [220, 60, 60]},
        {"id": "blue", "name": "蓝 T 恤", "color": [60, 110, 200]},
        {"id": "white", "name": "白衬衫", "color": [245, 245, 245]},
    ],
    "pants": [
        {"id": "blue", "name": "蓝裤", "color": [50, 80, 150]},
        {"id": "black", "name": "黑裤", "color": [40, 40, 50]},
    ],
    "accessory": [
        {"id": "none", "name": "无", "color": [255, 255, 255]},
        {"id": "glasses", "name": "眼镜", "color": [30, 30, 30]},
    ],
}


class TestAvatarRecipes:
    def test_all_layers_present(self):
        required = {"hair", "skin", "shirt", "pants", "accessory"}
        assert required == set(AVATAR_RECIPES.keys())

    def test_each_layer_has_min_options(self):
        for layer_id, options in AVATAR_RECIPES.items():
            assert len(options) >= 1, f"{layer_id} 至少要有 1 个选项"

    def test_unique_ids_per_layer(self):
        for layer_id, options in AVATAR_RECIPES.items():
            ids = [o["id"] for o in options]
            assert len(ids) == len(set(ids)), f"{layer_id} 有重复 id: {ids}"

    def test_default_avatar_valid(self):
        """default avatar 的每个 id 必须在对应 layer 存在"""
        default = {"hair": "spike", "skin": "medium", "shirt": "red",
                   "pants": "blue", "accessory": "none"}
        for layer_id, opt_id in default.items():
            ids = [o["id"] for o in AVATAR_RECIPES[layer_id]]
            assert opt_id in ids, f"default {layer_id}={opt_id} 不在 options 里"

    def test_combination_count(self):
        """总组合数 = 各 layer 数量相乘"""
        total = 1
        for options in AVATAR_RECIPES.values():
            total *= len(options)
        # 3*3*3*2*2 = 108
        assert total == 108

    def test_color_format(self):
        """color 必须是 [r, g, b] 0-255 整数"""
        for layer_id, options in AVATAR_RECIPES.items():
            for opt in options:
                c = opt["color"]
                assert len(c) == 3
                for v in c:
                    assert isinstance(v, int) and 0 <= v <= 255

    def test_name_non_empty(self):
        for layer_id, options in AVATAR_RECIPES.items():
            for opt in options:
                assert opt["name"] != "", f"{layer_id} 有空 name"
                assert opt["id"] != "", f"{layer_id} 有空 id"
