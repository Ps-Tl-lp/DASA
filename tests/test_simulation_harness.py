"""Harness contracts without PX4 or Gazebo dependencies."""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


flyer = load("px4_flyer")
harness = load("run_simulation")
recorder = load("gz_recorder")


def test_record_pose_exact_model_enu_and_clock():
    stream = io.StringIO()
    writer = recorder.PoseWriter(stream, "x500_0")

    def pose(name):
        return SimpleNamespace(name=name, position=SimpleNamespace(x=2, y=3, z=4))

    msg = SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=7, nsec=125000000)),
        pose=[pose("x500_0::link"), pose("x500_0")],
    )
    writer.receive(msg)
    assert json.loads(stream.getvalue()) == {"k": "pose", "t": 7.125, "p": [2, 3, 4]}
    assert writer.samples == 1


def test_invalid_pose_is_reported():
    writer = recorder.PoseWriter(io.StringIO(), "x500_0")
    writer.receive(SimpleNamespace(pose=[SimpleNamespace(name="x500_0")]))
    assert writer.error


def test_parameter_reference_resolution():
    assert harness.resolve({"tolerances": {"height": 0.8}}, "tolerances.height") == 0.8


def test_reject_unsupported_plan():
    with pytest.raises(ValueError, match="empty"):
        harness.plan_items({"fileType": "Plan", "mission": {"items": []}})


def test_fixture_plan_supported():
    plan = json.loads((SCRIPTS.parent / "tests/fixtures/m01/mission.plan").read_text())
    assert [i["command"] for i in harness.plan_items(plan)] == [22, 16, 20]


def test_build_failure_still_writes_documented_record(tmp_path):
    folder = tmp_path / "attempt"
    args = [
        "--plan",
        "missing.plan",
        "--start",
        "missing.xml",
        "--config",
        str(SCRIPTS.parent / "platform_configs/px4.yaml"),
        "--px4",
        str(tmp_path),
        "--mission-id",
        "M01",
        "--run-id",
        "R01",
        "--output",
        str(folder),
    ]
    with patch.object(harness.subprocess, "check_output", return_value="wrongbuild"):
        assert harness.main(args) == 2
    data = json.loads((folder / "run.json").read_text())
    assert data["run_status"] == "inconclusive"
    assert data["reason"] == "sim_setup"
    assert data["recording"] == "gz_pose.jsonl"
    assert data["log"] is None
    with pytest.raises(FileExistsError):
        harness.main(args)


def test_wait_has_wall_clock_deadline():
    instance = flyer.Flyer(None, lambda *a, **k: None, lambda: None)
    with (
        patch.object(flyer.time, "monotonic", side_effect=[0, 0, 301]),
        patch.object(instance, "receive", return_value=None),
    ):
        with pytest.raises(flyer.RunError) as error:
            instance.wait(lambda _: False, 300, "timeout")
    assert error.value.reason == "timeout"


def test_publisher_addresses_from_cli():
    result = SimpleNamespace(
        stdout="Publishers [Address, Message Type]:\n  tcp://host:123, gz.msgs.Pose_V\n"
    )
    with patch.object(recorder.subprocess, "run", return_value=result):
        assert recorder.publishers(None, "/pose") == [
            ["tcp://host:123", "gz.msgs.Pose_V"]
        ]


@pytest.mark.parametrize("disarm,expected", [(True, None), (False, "timeout")])
def test_flight_completion_and_timeout(disarm, expected):
    events = []
    instance = flyer.Flyer(None, lambda kind, **kw: events.append(kind), lambda: None)
    instance.last_heartbeat = 1
    instance.armed = True
    instance.airborne = True

    def receive():
        if disarm:
            instance.armed = False

    with (
        patch.object(instance, "wait"),
        patch.object(instance, "command"),
        patch.object(instance, "parameters", return_value={}),
        patch.object(instance, "upload"),
        patch.object(instance, "receive", receive),
        patch.object(flyer.time, "monotonic", side_effect=[0, 0, 1, 1, 301]),
    ):
        if expected:
            with pytest.raises(flyer.RunError) as error:
                instance.fly([], {}, 300)
            assert error.value.reason == expected
        else:
            assert instance.fly([], {}, 300) == {}
            assert "disarmed" in events
