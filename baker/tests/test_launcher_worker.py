import json
from pathlib import Path
from types import SimpleNamespace

from baker import launcher_worker
from baker.config import _default_config


def _submit(tmp_path, **fields):
    request = tmp_path / "request.json"
    parameters = {
        "mode": "coords",
        "input": "116.400,39.900\n116.405,39.905",
        "duration": 30,
        "output_dir": str(tmp_path),
        **fields,
    }
    request.write_text(json.dumps(parameters, ensure_ascii=False), encoding="utf-8")
    code = launcher_worker.main([str(request)])
    assert not request.exists()
    assert not (tmp_path / "result.json.tmp").exists()
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    return code, result


def test_worker_discards_invalid_request_contents(tmp_path, capsys):
    request = tmp_path / "request.json"
    request.write_text('{"amap_key": "invalid-private-value"', encoding="utf-8")
    assert launcher_worker.main([str(request)]) == 1
    assert not request.exists()
    assert "invalid-private-value" not in (tmp_path / "result.json").read_text(encoding="utf-8")
    assert not capsys.readouterr().out


def test_worker_requires_keys_for_diary(tmp_path, monkeypatch):
    monkeypatch.setattr("baker.config.load_config", _default_config)
    code, result = _submit(tmp_path, mode="text", input="我从王府井走到东单。")
    assert code == 1 and not result["ok"]
    assert "Key" in result["message"]


def test_worker_returns_only_routable_place_suggestions(tmp_path, monkeypatch):
    from baker.clients.amap import AmapClient

    def find(_self, query, city):
        assert query == "齐鑫花园" and city == "济宁"
        return [{"name": "齐鑫花园", "address": "任城区", "lng": 116.6, "lat": 35.4}]

    monkeypatch.setattr("baker.config.load_config", _default_config)
    monkeypatch.setattr(AmapClient, "suggest_places", find)
    code, result = _submit(tmp_path, mode="suggest", query="济宁市齐鑫花园", city="济宁", amap_key="test-value")
    assert code == 0 and result["ok"]
    assert [place["name"] for place in result["choices"]] == ["齐鑫花园"]
    assert "test-value" not in json.dumps(result)


def test_worker_rejects_route_without_osm_road_data(tmp_path, monkeypatch):
    def unavailable(*_):
        return SimpleNamespace(run=lambda: None, _render_ctx={"osm": {"roads": []}})

    monkeypatch.setattr("baker.modes.CoordsMode", unavailable)
    code, result = _submit(tmp_path)
    assert code == 1 and not result["ok"]
    assert "OpenStreetMap" in result["message"]
    assert not (tmp_path / "route.json").exists()


def test_worker_returns_only_safe_result_with_a_rendered_path(tmp_path, monkeypatch, capsys):
    from baker.core.schema import LogPayload, Waypoint

    class Route:
        def __init__(self, name, coordinates, config):
            assert coordinates == "116.4,39.9;116.405,39.905"
            assert not (tmp_path / "request.json").exists()
            assert config["amap"]["timeout_sec"] == 8
            assert config["bake"]["osm_timeout_sec"] == 12
            self.output = Path(config["bake"]["output_dir"])
            self.name = name
            self._render_ctx = {"osm": {"roads": [{}]}}
            self.payload = LogPayload(path=[Waypoint(), Waypoint(x=1, y=1, t=60)])

        def run(self):
            self.progress_callback("map")
            progress = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
            assert progress == {"stage": "map"}
            print("potentially sensitive upstream diagnostics")
            return self.payload

        def write(self):
            assert self.payload.path[-1].t == 30
            path = self.output / f"{self.name}.json"
            path.write_text("{}", encoding="utf-8")
            path.with_name(f"{self.name}_map.png").touch()
            return path

    monkeypatch.setattr("baker.modes.CoordsMode", Route)
    code, result = _submit(tmp_path)
    assert code == 0 and result["ok"]
    assert Path(result["log_path"]) == tmp_path / "route.json"
    assert json.loads((tmp_path / "progress.json").read_text(encoding="utf-8")) == {"stage": "render"}
    assert not (tmp_path / "progress.json.tmp").exists()
    assert not capsys.readouterr().out
