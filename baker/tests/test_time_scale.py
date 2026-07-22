"""测试 baker/core/time_scale.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from baker.core.time_scale import apply_time_scale, normalize_dialog_times
from baker.core.schema import LogPayload, Waypoint, Dialog, Meta


class TestNormalizeDialogTimes:
    def test_t_offset_to_seconds(self):
        dialogs = [{"t_offset": 0.0, "speaker": "Me", "text": "a"},
                   {"t_offset": 0.5, "speaker": "老张", "text": "b"},
                   {"t_offset": 1.0, "speaker": "Me", "text": "c"}]
        out = normalize_dialog_times(dialogs, 100.0)
        assert out[0]["t"] == 0.0
        assert out[1]["t"] == 50.0
        assert out[2]["t"] == 100.0
        # t_offset 字段被去掉
        assert "t_offset" not in out[0]

    def test_already_has_t(self):
        dialogs = [{"t": 5.0, "speaker": "Me", "text": "a"}]
        out = normalize_dialog_times(dialogs, 100.0)
        assert out[0]["t"] == 5.0

    def test_no_t_no_offset_uniform(self):
        dialogs = [{"speaker": "Me", "text": "a"},
                   {"speaker": "Me", "text": "b"}]
        out = normalize_dialog_times(dialogs, 100.0)
        # 第 1 个 0%, 第 2 个 95% (i/(n-1)*0.95)
        assert out[0]["t"] == 0.0
        assert abs(out[1]["t"] - 95.0) < 0.01

    def test_empty(self):
        assert normalize_dialog_times([], 100.0) == []


class TestApplyTimeScale:
    def test_dict_payload(self):
        payload = {
            "path": [{"t": 0}, {"t": 100}, {"t": 200}],
            "dialogs": [{"t": 50}],
            "meta": {},
        }
        apply_time_scale(payload, 30.0)
        # 比例 30/200 = 0.15
        assert payload["path"][0]["t"] == 0
        assert abs(payload["path"][1]["t"] - 15.0) < 0.1
        assert abs(payload["path"][2]["t"] - 30.0) < 0.1
        assert abs(payload["dialogs"][0]["t"] - 7.5) < 0.1
        # meta 记录
        assert payload["meta"]["original_duration_sec"] == 200
        assert payload["meta"]["scaled_duration_sec"] == 30.0

    def test_logpayload_object(self):
        p = LogPayload()
        p.path.append(Waypoint(x=0, y=0, t=0.0))
        p.path.append(Waypoint(x=5, y=0, t=100.0))
        p.dialogs.append(Dialog(t=50.0, speaker="Me", text=""))
        apply_time_scale(p, 10.0)
        assert p.path[0].t == 0
        assert abs(p.path[1].t - 10.0) < 0.1
        assert abs(p.dialogs[0].t - 5.0) < 0.1
        assert p.meta.original_duration_sec == 100.0
        assert p.meta.scaled_duration_sec == 10.0

    def test_zero_target_noop(self):
        payload = {"path": [{"t": 100}], "dialogs": []}
        apply_time_scale(payload, 0)
        assert payload["path"][0]["t"] == 100

    def test_empty_path(self):
        payload = {"path": [], "dialogs": []}
        apply_time_scale(payload, 30.0)
        # 不崩
        assert payload["path"] == []
