"""测试 baker/clients/osm.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.clients.osm import (
    OsmClient, parse_overpass, compute_bbox_from_points, expand_bbox,
)


class TestBboxQuery:
    def test_basic_ql(self):
        ql = OsmClient.build_bbox_query((39.90, 116.39, 39.92, 116.41))
        assert "[out:json]" in ql
        # Python float toString 去掉尾随 0, 所以用 39.9,116.39,39.92,116.41
        assert "39.9,116.39,39.92,116.41" in ql
        assert 'way["highway"]' in ql
        assert 'way["building"]' in ql
        assert 'way["waterway"]' in ql
        assert 'way["leisure"="park"]' in ql


class TestBboxUtils:
    def test_compute_from_points(self):
        pts = [(39.90, 116.39), (39.92, 116.41)]
        bbox = compute_bbox_from_points(pts, pad_ratio=0.1)
        # min_lat=39.90, max_lat=39.92, min_lng=116.39, max_lng=116.41
        # pad: 0.002 lat, 0.002 lng
        assert bbox[0] < 39.90
        assert bbox[1] < 116.39
        assert bbox[2] > 39.92
        assert bbox[3] > 116.41

    def test_compute_empty(self):
        bbox = compute_bbox_from_points([])
        assert bbox == (0.0, 0.0, 0.001, 0.001)

    def test_expand_too_small(self):
        # 0.001° 太窄, 扩到 0.008°
        bbox = (39.90, 116.39, 39.901, 116.391)
        expanded = expand_bbox(bbox, min_size_deg=0.008)
        h = expanded[2] - expanded[0]
        w = expanded[3] - expanded[1]
        # 浮点容差
        assert h >= 0.0079
        assert w >= 0.0079

    def test_expand_already_big(self):
        # 已经够大, 不动
        bbox = (39.90, 116.39, 39.92, 116.41)
        expanded = expand_bbox(bbox, min_size_deg=0.008)
        assert expanded == bbox


class TestParseOverpass:
    def test_basic_parse(self):
        """模拟一个 OSM JSON 响应"""
        raw = {
            "elements": [
                # nodes
                {"type": "node", "id": 1, "lat": 39.90, "lon": 116.40},
                {"type": "node", "id": 2, "lat": 39.91, "lon": 116.41},
                {"type": "node", "id": 3, "lat": 39.92, "lon": 116.42},
                # highway way
                {"type": "way", "id": 100, "nodes": [1, 2, 3],
                 "tags": {"highway": "primary", "name": "长安街"}},
                # building way (闭环)
                {"type": "way", "id": 200, "nodes": [1, 2, 3, 1],
                 "tags": {"building": "yes", "name": ""}},
                # water
                {"type": "way", "id": 300, "nodes": [1, 2],
                 "tags": {"waterway": "river"}},
                # park
                {"type": "way", "id": 400, "nodes": [1, 2, 3],
                 "tags": {"leisure": "park"}},
            ]
        }
        result = parse_overpass(raw)
        assert len(result["roads"]) == 1
        assert result["roads"][0]["highway_type"] == "primary"
        assert result["roads"][0]["name"] == "长安街"
        assert len(result["roads"][0]["nodes"]) == 3

        assert len(result["buildings"]) == 1
        assert result["buildings"][0]["building"] == "yes"

        assert len(result["water"]) == 1
        assert result["water"][0]["type"] == "river"

        assert len(result["green"]) == 1
        assert result["green"][0]["kind"] == "park"

    def test_skip_orphan_nodes(self):
        """way 引用了不存在的 node, 跳过"""
        raw = {
            "elements": [
                {"type": "way", "id": 100, "nodes": [999, 888],
                 "tags": {"highway": "primary"}},
            ]
        }
        result = parse_overpass(raw)
        assert result["roads"] == []

    def test_skip_short_ways(self):
        """只有 1 个 node 的 way 跳过"""
        raw = {
            "elements": [
                {"type": "node", "id": 1, "lat": 39.9, "lon": 116.4},
                {"type": "way", "id": 100, "nodes": [1],  # 单点
                 "tags": {"highway": "primary"}},
            ]
        }
        result = parse_overpass(raw)
        assert result["roads"] == []
