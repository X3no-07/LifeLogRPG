"""多边形水体 (multipolygon) 与并道上限测试。"""
from baker.clients.osm import parse_overpass, parse_osm_api_xml
from baker.core.gridifier import osm_to_grid
from baker.render.firered import _merge_parallel_lanes


def _mp_raw():
    # 外环正方形拆成两条 way (第二条反向拼), 内环一个小正方形 (岛)。
    # 节点 (lon, lat); way 本身无标签, 只靠 relation 认出是湖。
    nodes = [
        {"type": "node", "id": 1, "lon": 0.0, "lat": 0.0},
        {"type": "node", "id": 2, "lon": 1.0, "lat": 0.0},
        {"type": "node", "id": 3, "lon": 1.0, "lat": 1.0},
        {"type": "node", "id": 4, "lon": 0.0, "lat": 1.0},
        {"type": "node", "id": 5, "lon": 0.4, "lat": 0.4},
        {"type": "node", "id": 6, "lon": 0.6, "lat": 0.4},
        {"type": "node", "id": 7, "lon": 0.6, "lat": 0.6},
        {"type": "node", "id": 8, "lon": 0.4, "lat": 0.6},
    ]
    ways = [
        {"type": "way", "id": 10, "nodes": [1, 2, 3], "tags": {}},
        {"type": "way", "id": 11, "nodes": [3, 4, 1], "tags": {}},
        {"type": "way", "id": 12, "nodes": [5, 6, 7, 8, 5], "tags": {}},
    ]
    rel = {"type": "relation", "id": 99,
           "members": [{"type": "way", "ref": 10, "role": "outer"},
                       {"type": "way", "ref": 11, "role": "outer"},
                       {"type": "way", "ref": 12, "role": "inner"}],
           "tags": {"type": "multipolygon", "natural": "water",
                    "name": "测试湖"}}
    return {"elements": nodes + ways + [rel]}


def test_multipolygon_water_stitched():
    parsed = parse_overpass(_mp_raw())
    assert len(parsed["water"]) == 1
    lake = parsed["water"][0]
    assert lake["name"] == "测试湖"
    # 外环拼成闭合环 (首尾同点)
    assert lake["nodes"][0] == lake["nodes"][-1]
    assert set(lake["nodes"]) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}
    # 内环挂 holes
    assert len(lake["holes"]) == 1
    assert set(lake["holes"][0]) == {(0.4, 0.4), (0.6, 0.4),
                                     (0.6, 0.6), (0.4, 0.6)}


def test_multipolygon_non_water_ignored():
    raw = _mp_raw()
    raw["elements"][-1]["tags"] = {"type": "multipolygon",
                                   "boundary": "administrative",
                                   "name": "某区"}
    parsed = parse_overpass(raw)
    assert parsed["water"] == []


def test_osm_api_xml_keeps_relations():
    xml = """<osm><node id="1" lat="0.0" lon="0.0"/>
    <way id="10"><nd ref="1"/><tag k="natural" v="water"/></way>
    <relation id="99"><member type="way" ref="10" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="natural" v="water"/></relation></osm>"""
    parsed = parse_osm_api_xml(xml)
    rels = [e for e in parsed["elements"] if e["type"] == "relation"]
    assert len(rels) == 1
    assert rels[0]["members"] == [{"type": "way", "ref": 10, "role": "outer"}]
    assert rels[0]["tags"]["natural"] == "water"


def test_osm_to_grid_water_holes_punched_back():
    parsed = {"roads": [], "buildings": [], "green": [], "ground": [],
              "water": [{"type": "lake", "name": "", "nodes": [
                  (0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)],
                  "holes": [[(0.4, 0.4), (0.6, 0.4), (0.6, 0.6),
                             (0.4, 0.6), (0.4, 0.4)]]}]}
    grid, _, _ = osm_to_grid(parsed, (0.0, 0.0, 1.0, 1.0), (10, 10))
    assert grid[1][1] == 3  # 湖内是水
    assert grid[5][5] != 3  # 岛抠回陆地 (底色)


def test_merge_parallel_lanes_wide_group_not_merged():
    # 5 条南北向平行路, 中心线每 5 格一条 (链式并组、总跨度 20 格):
    # 不是一条大道, 不能并成一张灰板, 应原样保留、每条宽不变。
    roads = [{"pts": [(float(x), 0.0), (float(x), 100.0)], "w": 2,
              "type": "residential"} for x in (0, 5, 10, 15, 20)]
    out = _merge_parallel_lanes(roads)
    assert len(out) == 5
    assert max(r["w"] for r in out) == 2


def test_merge_parallel_lanes_real_avenue_merges():
    # 两条平行车道 (中心线差 4 格) + 一条非机动车道: 应并成一条宽路。
    roads = [
        {"pts": [(0.0, 0.0), (100.0, 0.0)], "w": 3, "type": "trunk"},
        {"pts": [(0.0, 4.0), (100.0, 4.0)], "w": 3, "type": "trunk"},
        {"pts": [(0.0, 7.0), (100.0, 7.0)], "w": 1, "type": "cycleway"},
    ]
    out = _merge_parallel_lanes(roads)
    assert len(out) == 1
    assert 1 < out[0]["w"] <= 12
