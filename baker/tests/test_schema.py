"""测试 baker/core/schema.py 数据契约"""
import pytest
import time
import sys
from pathlib import Path

# 允许从 baker 根目录导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.schema import (
    LogPayload, Waypoint, Dialog, MapData, Meta, Character,
)


class TestMeta:
    def test_default_values(self):
        m = Meta()
        assert m.log_id == ""
        assert m.weather == "unknown"
        assert m.mood == "calm"

    def test_to_dict(self):
        m = Meta(log_id="log_001", title="测试", weather="sunny")
        d = m.to_dict()
        assert d["log_id"] == "log_001"
        assert d["weather"] == "sunny"
        assert d["mood"] == "calm"  # 默认


class TestWaypoint:
    def test_construction(self):
        wp = Waypoint(x=5, y=10, t=3.5, label="home", transport="walking")
        assert wp.x == 5
        assert wp.y == 10
        assert wp.t == 3.5
        assert wp.transport == "walking"

    def test_default_transport_is_walking(self):
        wp = Waypoint()
        assert wp.transport == "walking"

    def test_to_dict_keys(self):
        wp = Waypoint(x=1, y=2, t=0.0).to_dict()
        assert set(wp.keys()) >= {"x", "y", "t", "label", "transport"}


class TestLogPayload:
    def test_to_dict_structure(self):
        p = LogPayload()
        p.meta.log_id = "log_001"
        p.path.append(Waypoint(x=1, y=2, t=0.0, transport="walking"))
        p.dialogs.append(Dialog(t=1.0, speaker="Me", text="hi"))
        d = p.to_dict()
        assert "meta" in d
        assert "map" in d
        assert "path" in d
        assert "dialogs" in d
        assert "characters" in d
        assert d["path"][0]["x"] == 1
        assert d["dialogs"][0]["text"] == "hi"

    def test_default_characters(self):
        """LogPayload 默认 characters 为空 (BaseMode 才会主动 push 'Me')"""
        p = LogPayload()
        assert len(p.characters) == 0


class TestMapData:
    def test_default_legend(self):
        m = MapData()
        assert m.legend["0"] == "grass"
        assert m.legend["1"] == "road"
        assert m.legend["4"] == "tree"

    def test_grid_independence(self):
        """每个实例的 grid 应该是独立的 list (不共享引用)"""
        m1 = MapData()
        m2 = MapData()
        m1.grid.append([1, 2, 3])
        assert m2.grid == []  # 不被 m1 影响
