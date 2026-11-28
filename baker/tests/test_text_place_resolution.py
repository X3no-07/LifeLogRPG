from types import SimpleNamespace

import pytest

from baker.config import _default_config
from baker.modes.text import PlaceResolutionError, TextMode


@pytest.fixture
def diary():
    config = _default_config()
    config["bake"]["default_city"] = "济宁"
    return TextMode("route", "下午从济宁市齐鑫花园到济宁市万达广场", config)


def test_explicit_route_keeps_the_named_endpoints(diary):
    assert diary._extract_places() == ["济宁市齐鑫花园", "济宁市万达广场"]


def test_unrelated_first_poi_is_rejected(diary):
    diary.amap = SimpleNamespace(
        place_candidates=lambda *args, **kwargs: [(116.6, 35.4, "济宁市万耐机械有限公司")]
    )
    with pytest.raises(PlaceResolutionError, match="找不到与「济宁市齐鑫花园」匹配"):
        diary._geocode_all(diary._extract_places())


def test_named_branch_is_resolved_without_adding_other_branches(diary):
    garden = (116.61, 35.41, "齐鑫花园")
    jianshe = (116.62, 35.42, "万达广场(建设路店)")
    taibai = (116.63, 35.43, "万达广场(任城太白路店)")

    def candidates(query, *, city):
        assert city == "济宁"
        if query == "齐鑫花园":
            return [(116.6, 35.4, "济宁市万耐机械有限公司"), garden]
        return [jianshe, taibai]

    diary.amap = SimpleNamespace(place_candidates=candidates)
    with pytest.raises(PlaceResolutionError, match="多个匹配地点"):
        diary._geocode_all(diary._extract_places())

    diary.text = "下午从济宁市齐鑫花园到济宁市万达广场（任城太白路店）"
    resolved = diary._geocode_all(diary._extract_places())
    assert [place["name"] for place in resolved] == [garden[2], taibai[2]]

    diary.text = "从济宁市齐鑫花园到济宁市万达广场任城太白路店"
    diary.amap.place_candidates = lambda query, **kwargs: (
        [] if query.endswith("太白路店") else candidates(query, **kwargs)
    )
    resolved = diary._geocode_all(diary._extract_places())
    assert [place["name"] for place in resolved] == [garden[2], taibai[2]]
