from baker.clients.osm import parse_osm_api_xml, parse_overpass
from baker.core.gridifier import project_walking_track
from baker.core.schema import LogPayload, MapData, Waypoint
from baker.core.stops import build_stops
from baker.core.time_scale import apply_time_scale


BOUNDS = (39.90, 116.40, 39.91, 116.41)
XML = """
<osm>
  <node id="1" lon="116.404" lat="39.906" />
  <node id="2" lon="116.406" lat="39.906"><tag k="entrance" v="main" /></node>
  <node id="3" lon="116.406" lat="39.904" />
  <node id="4" lon="116.404" lat="39.904">
    <tag k="entrance" v="yes" /><tag k="access" v="private" />
  </node>
  <node id="5" lon="116.403" lat="39.903">
    <tag k="amenity" v="cafe" /><tag k="name" v="咖啡店甲" />
  </node>
  <way id="6">
    <nd ref="1" /><nd ref="2" /><nd ref="3" /><nd ref="4" /><nd ref="1" />
    <tag k="building" v="yes" /><tag k="shop" v="books" />
    <tag k="name" v="Bookshop A" /><tag k="name:zh-Hans" v="书店甲" />
  </way>
</osm>
"""


def _payload(*waypoints):
    return LogPayload(map=MapData(width=100, height=100),
                      path=[Waypoint(x=x, y=y, t=t) for x, y, t in waypoints])


def test_stops_use_verified_osm_building_and_public_entrance():
    osm = parse_overpass(parse_osm_api_xml(XML))
    assert osm["buildings"][0]["entrances"] == [(116.406, 39.906)]
    payload = _payload((10, 70, 0), (30, 70, 20), (50, 61, 60))
    payload.stops = build_stops(payload, [(116.401, 39.903), (116.403, 39.903),
                                         (116.405, 39.905)], BOUNDS, osm)
    assert [(s.name, s.category) for s in payload.stops] == [("咖啡店甲", "咖啡店"), ("书店甲", "书店")]
    assert payload.stops[0].t < payload.stops[1].t
    assert payload.stops[0].outline == []
    assert len(payload.stops[1].outline) == 4
    assert payload.stops[1].entrance
    assert abs(payload.stops[1].x - 59.5) < 0.001
    assert abs(payload.stops[1].y - 39.5) < 0.001
    original_intermediate_time = payload.stops[0].t
    apply_time_scale(payload, 30)
    assert payload.stops[0].t == round(original_intermediate_time / 2, 2)
    assert payload.to_dict()["stops"][1]["t"] == payload.path[-1].t == 30


def test_unmapped_entrance_uses_building_side_facing_route():
    osm = parse_overpass(parse_osm_api_xml(XML))
    osm["buildings"][0]["entrances"] = []
    payload = _payload((20, 75, 0), (50, 63, 90))
    stop, = build_stops(payload, [(116.402, 39.9025), (116.405, 39.905)], BOUNDS, osm)
    assert stop.name == "书店甲"
    assert not stop.entrance
    assert abs(stop.y - 59.5) < 0.001


def test_unknown_finish_does_not_name_unrelated_building_or_clamp_off_map_name():
    osm = parse_overpass(parse_osm_api_xml(XML))
    payload = _payload((20, 14, 0), (46, 20, 45))
    assert "stops" not in payload.to_dict()
    unnamed, = build_stops(payload, [(116.402, 39.9086), (116.4046, 39.908)], BOUNDS, osm)
    assert (unnamed.x, unnamed.y, unnamed.t) == (46, 20, 45)
    assert not unnamed.name and not unnamed.category and not unnamed.outline
    off_map, = build_stops(payload, [(116.402, 39.9086), (116.420, 39.915)], BOUNDS, osm,
                           ["出发点", "地图外的目的地"])
    assert off_map == unnamed


def test_mismatched_containing_building_does_not_override_text_destination():
    osm = parse_overpass(parse_osm_api_xml(XML))
    payload = _payload((20, 75, 0), (50, 63, 75))
    stop, = build_stops(payload, [(116.402, 39.9025), (116.405, 39.905)], BOUNDS, osm,
                        ["出发点", "另外一家店"])
    assert stop.name == "另外一家店"
    assert not stop.category and not stop.outline and not stop.entrance


def test_confirmed_walking_destination_has_pin_without_an_osm_building():
    payload = _payload((10, 70, 0), (50, 72, 45))
    stop, = build_stops(
        payload, [(116.401, 39.903), (116.405, 39.905)], BOUNDS, {},
        ["小区北门", "万达广场"], confirmed_finish=True,
    )
    assert stop.name == "万达广场" and stop.t == 45
    assert abs(stop.x - 49.5) < 0.001 and abs(stop.y - 49.5) < 0.001
    assert not stop.outline and not stop.entrance


def test_walking_track_keeps_geographic_corners_and_subcell_coordinates():
    bounds = (0, 0, 1, 1)
    route = [(0.25, 0.75), (0.25001, 0.74999), (0.25, 0.25), (0.75, 0.25)]
    assert project_walking_track(route, bounds, (40, 40), 16) == [
        {"x": 9.5, "y": 9.5}, {"x": 9.5, "y": 29.5}, {"x": 29.5, "y": 29.5},
    ]
