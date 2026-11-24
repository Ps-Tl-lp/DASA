"""Tests for the wired pipeline: the pieces calling each other.

Expected values come from the M01 fixture and the config, not from the pieces' own
output.
"""

import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
M01 = ROOT / "tests" / "fixtures" / "m01"
CONFIG = ROOT / "platform_configs" / "px4.yaml"
sys.path.insert(0, str(ROOT / "scripts"))

from generate_mission import GeneratorError, generate  # noqa: E402
from run_mission import main as run_mission  # noqa: E402

from plan_step import plan_mission, plan_text  # noqa: E402
from plan_step.config import load_config  # noqa: E402
from verifier.cli import main as verify  # noqa: E402
from verifier.loaders import load_mission  # noqa: E402
from verifier.models import PostconditionSpec  # noqa: E402

# ---- The generator asks the plan step ------------------------------------------------


def _config_copy(tmp_path, change):
    config = yaml.safe_load(CONFIG.read_text())
    change(config)
    path = tmp_path / "px4.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


@pytest.mark.parametrize("seed", [7, 11, 42])
def test_a_generated_mission_has_a_plan_with_the_settings_hold(seed):
    result = generate(M01 / "start.xml", M01 / "simple.yaml", CONFIG, seed)
    settings = yaml.safe_load((M01 / "simple.yaml").read_text())
    plan = plan_mission(result["start"], result["goal"], settings, load_config())
    items = plan["mission"]["items"]
    # takeoff, a goto holding simple.yaml's 5 s, return to launch (MAV_CMD 22, 16, 20)
    assert [item["command"] for item in items] == [22, 16, 20]
    assert items[1]["params"][0] == 5
    assert plan_text(plan).startswith("{")


def test_a_mission_the_drone_cant_fly_stops_the_generator(tmp_path):
    # Takeoff that needs a camera the least-equipped type doesn't have: no task list
    # can fly the mission.
    def needs_camera(config):
        config["tasks"]["takeoff"]["needs"]["agent.has_camera"] = True

    config = _config_copy(tmp_path, needs_camera)
    with pytest.raises(GeneratorError, match="has no plan"):
        generate(M01 / "start.xml", M01 / "simple.yaml", config, 7)


def test_a_mission_the_plan_step_cant_plan_stops_the_generator(tmp_path):
    def no_takeoff(config):
        del config["tasks"]["takeoff"]

    config = _config_copy(tmp_path, no_takeoff)
    with pytest.raises(GeneratorError, match="plan step can't plan"):
        generate(M01 / "start.xml", M01 / "simple.yaml", config, 7)


# ---- The verifier reads the mission folder -------------------------------------------


def _checks(verdict):
    return [(c["check"], c.get("waypoint"), c["verdict"]) for c in verdict["checks"]]


@pytest.mark.parametrize("mission", ["folder", "settings file"])
@pytest.mark.parametrize("run", ["R01", "R02"])
def test_the_verifier_reads_the_mission_folder_and_gets_the_fixture_verdicts(
    tmp_path, mission, run
):
    path = M01 if mission == "folder" else M01 / "simple.yaml"
    run_dir = M01 if run == "R01" else M01 / run
    out = tmp_path / "verdict.json"
    args = [str(path), str(run_dir / "readings.json"), "--config", str(CONFIG)]
    assert verify([*args, "--output", str(out)]) == 0
    got = json.loads(out.read_text())
    want = json.loads((run_dir / "expected-verdict.json").read_text())
    assert got["verdict"] == want["verdict"]
    assert _checks(got) == _checks(want)


def test_hold_at_each_waypoint_becomes_a_hold_at_for_every_waypoint():
    mission, start, _goal = load_mission(M01)
    assert mission.mission_id == "M01"
    assert mission.postconditions == (
        PostconditionSpec(name="hold_at", params={"waypoint": "W1", "min_s": 5}),
    )
    assert list(start.waypoints) == ["W1"]


def test_the_older_mission_yaml_still_reads_the_same(tmp_path):
    for name in ("start.xml", "goal.xml"):
        shutil.copy(M01 / name, tmp_path / name)
    (tmp_path / "mission.yaml").write_text(
        "mission_id: M01\nstart: start.xml\ngoal: goal.xml\n"
        "postconditions:\n  - hold_at: {waypoint: W1, min_s: 5}\n"
    )
    assert load_mission(tmp_path / "mission.yaml") == load_mission(M01)


def test_a_mission_folder_with_two_settings_files_is_an_error(tmp_path):
    for name in ("start.xml", "goal.xml", "simple.yaml"):
        shutil.copy(M01 / name, tmp_path / name)
    shutil.copy(M01 / "simple.yaml", tmp_path / "other.yaml")
    with pytest.raises(ValueError, match="one"):
        load_mission(tmp_path)


# ---- One command for the whole chain (scripts/run_mission.py) -----------------------


def _m01_mission(folder):
    folder.mkdir(parents=True)
    for name in ("start.xml", "goal.xml", "simple.yaml", "mission.plan"):
        shutil.copy(M01 / name, folder / name)
    return folder


def test_the_runner_generates_and_plans_then_stops_without_a_flight(tmp_path):
    out = tmp_path / "mission"
    args = [
        "--template",
        str(M01 / "start.xml"),
        "--settings",
        str(M01 / "simple.yaml"),
    ]
    assert run_mission([*args, "--out", str(out), "--seed", "7"]) == 2
    names = sorted(path.name for path in out.iterdir())
    assert names == ["goal.xml", "mission.plan", "simple.yaml", "start.xml"]
    assert (out / "simple.yaml").read_bytes() == (M01 / "simple.yaml").read_bytes()
    # The plan written is the one the generator's own check found for its states.
    settings = yaml.safe_load((M01 / "simple.yaml").read_text())
    states = [(out / name).read_text() for name in ("start.xml", "goal.xml")]
    expected = plan_text(plan_mission(*states, settings, load_config()))
    assert (out / "mission.plan").read_text() == expected


def test_the_runner_refuses_a_mission_plan_that_isnt_the_plan_steps(tmp_path):
    mission = _m01_mission(tmp_path / "m01")
    (mission / "mission.plan").write_text("{}\n")
    assert run_mission(["--mission", str(mission)]) == 1
    assert (mission / "mission.plan").read_text() == "{}\n"  # left as it was


def test_a_run_with_no_log_is_inconclusive(tmp_path):
    mission = _m01_mission(tmp_path / "m01")
    run = mission / "R009"
    run.mkdir()
    # What the harness writes when the setup fails (tests/fixtures/m01/README.md).
    record = {
        "mission_id": "M01",
        "run_id": "R009",
        "plan": "mission.plan",
        "run_status": "inconclusive",
        "reason": "sim_setup",
        "source": "simulator",
        "log": None,
        "recording": "gz_pose.jsonl",
        "record": {},
    }
    (run / "run.json").write_text(json.dumps(record))
    # Decided: a run with no flight log is INCONCLUSIVE.
    assert run_mission(["--mission", str(mission), "--run", str(run)]) == 0
    verdict = json.loads((run / "verdict.json").read_text())
    assert verdict["verdict"] == "INCONCLUSIVE"
    assert {check["verdict"] for check in verdict["checks"]} == {"INCONCLUSIVE"}
    readings = json.loads((run / "readings.json").read_text())
    assert "no flight log" in readings["log_problem"]


@pytest.mark.parametrize("settings_name", ["simple.yaml", "px4.yaml"])
def test_the_harness_keeps_the_goal_and_settings_with_the_run(tmp_path, settings_name):
    # Only the copy step is tested: the build check, pymavlink and Linux are faked, and
    # the simulator fails to start, so nothing is flown.
    import run_simulation

    mission = _m01_mission(tmp_path / "m01")
    # Settings named px4.yaml must not replace the config the run was flown with.
    settings = tmp_path / "settings-source" / settings_name
    settings.parent.mkdir()
    shutil.copy(mission / "simple.yaml", settings)
    run = tmp_path / "R001"
    args = [
        "--plan", str(mission / "mission.plan"),
        "--start", str(mission / "start.xml"),
        "--goal", str(mission / "goal.xml"),
        "--settings", str(settings),
        "--config", str(CONFIG),
        "--px4", str(tmp_path),
        "--mission-id", "M01",
        "--run-id", "R001",
        "--output", str(run),
    ]  # fmt: skip
    build = yaml.safe_load(CONFIG.read_text())["sim"]["px4_build"]
    pymavlink = SimpleNamespace(mavutil=SimpleNamespace())
    with (
        patch.object(run_simulation.subprocess, "check_output", return_value=build),
        patch.dict(sys.modules, {"pymavlink": pymavlink}),
        patch.object(run_simulation.sys, "platform", "linux"),
        patch.object(run_simulation.subprocess, "Popen", side_effect=OSError("no sim")),
    ):
        assert run_simulation.main(args) == 2  # the simulator didn't start
    for name in ("mission.plan", "start.xml", "goal.xml", "settings.yaml", "px4.yaml"):
        assert (run / name).is_file(), name
    assert (run / "goal.xml").read_bytes() == (M01 / "goal.xml").read_bytes()
    # The settings get a fixed name, so they can't replace the config.
    assert (run / "settings.yaml").read_bytes() == (M01 / "simple.yaml").read_bytes()
    assert (run / "px4.yaml").read_bytes() == CONFIG.read_bytes()
    assert json.loads((run / "run.json").read_text())["reason"] == "sim_setup"


@pytest.mark.skipif(
    not os.environ.get("HYDRA_R02_ULG"), reason="set HYDRA_R02_ULG to R02.ulg"
)
def test_the_runner_verifies_r02_from_its_log_as_the_fixture_says(tmp_path):
    mission = _m01_mission(tmp_path / "m01")
    run = mission / "R02"
    run.mkdir()
    shutil.copy(M01 / "R02" / "run.json", run / "run.json")
    shutil.copy(os.environ["HYDRA_R02_ULG"], run / "R02.ulg")
    assert run_mission(["--mission", str(mission), "--run", str(run)]) == 0
    got = json.loads((run / "verdict.json").read_text())
    want = json.loads((M01 / "R02" / "expected-verdict.json").read_text())
    assert got["verdict"] == want["verdict"] == "PASS"
    assert _checks(got) == _checks(want)
    # A second read of the same run is refused rather than written over.
    assert run_mission(["--mission", str(mission), "--run", str(run)]) == 1


# ---- What the verifier's mission loader refuses or skips -----------------------------


def _two_waypoint_mission(folder, postconditions):
    import test_plan_step as plan_tests  # its _mission writes both states and settings

    return plan_tests._mission(
        folder, {"W1": (40, 0, 20), "W2": (0, 40, 20)}, postconditions
    )


def test_every_waypoint_gets_exactly_one_hold(tmp_path):
    mission = _two_waypoint_mission(tmp_path, {"hold_at_each_waypoint": {"min_s": 5}})
    loaded, _start, _goal = load_mission(mission)
    assert loaded.postconditions == (
        PostconditionSpec(name="hold_at", params={"waypoint": "W1", "min_s": 5}),
        PostconditionSpec(name="hold_at", params={"waypoint": "W2", "min_s": 5}),
    )


@pytest.mark.parametrize(
    "fields",
    [{"min_s": 5, "waypoint": "W1"}, {"min_s": -3}, {"min_s": "five"}, {}],
    ids=["a waypoint field", "a negative hold", "a hold as text", "no hold time"],
)
def test_a_hold_written_wrong_is_an_error(tmp_path, fields):
    # The same rules as the plan step: hold_at_each_waypoint takes only min_s, a
    # number of seconds. An extra waypoint field could otherwise check W1 twice and W2
    # never.
    mission = _two_waypoint_mission(tmp_path, {"hold_at_each_waypoint": fields})
    with pytest.raises(ValueError, match="hold_at_each_waypoint"):
        load_mission(mission)


def test_start_and_goal_with_different_waypoints_are_an_error(tmp_path):
    two = _two_waypoint_mission(tmp_path / "two", {})
    one = M01
    mission = tmp_path / "mixed"
    mission.mkdir()
    shutil.copy(one / "start.xml", mission / "start.xml")
    shutil.copy(two / "goal.xml", mission / "goal.xml")
    shutil.copy(one / "simple.yaml", mission / "simple.yaml")
    with pytest.raises(ValueError, match="waypoints"):
        load_mission(mission)


def test_a_listed_disarmed_after_landing_is_checked_once(tmp_path):
    # The verifier always runs disarmed_after_landing, so listing it in the settings
    # must change nothing, not stop the verifier with "Unsupported postcondition".
    mission = tmp_path / "m01"
    shutil.copytree(M01, mission)
    settings = mission / "simple.yaml"
    settings.write_text(settings.read_text() + "  disarmed_after_landing: {}\n")
    out = tmp_path / "verdict.json"
    readings = M01 / "R02" / "readings.json"
    args = [str(mission), str(readings), "--config", str(CONFIG), "--output", str(out)]
    assert verify(args) == 0
    checks = [c["check"] for c in json.loads(out.read_text())["checks"]]
    assert checks.count("disarmed_after_landing") == 1


# ---- Replaying a run that was already flown ------------------------------------------


def _kept_run(folder):
    """A run folder as the harness keeps one, made from the M01 fixture and R02."""
    folder.mkdir(parents=True)
    for name in ("start.xml", "goal.xml", "mission.plan"):
        shutil.copy(M01 / name, folder / name)
    shutil.copy(M01 / "simple.yaml", folder / "settings.yaml")
    shutil.copy(CONFIG, folder / "px4.yaml")
    record = json.loads((M01 / "R02" / "run.json").read_text())
    record["plan"] = "mission.plan"
    (folder / "run.json").write_text(json.dumps(record))
    return folder


def test_a_run_replayed_against_another_mission_is_refused(tmp_path, capsys):
    run = _kept_run(tmp_path / "run")
    other = _m01_mission(tmp_path / "other")
    settings = other / "simple.yaml"
    settings.write_text(
        settings.read_text().replace("mission_id: M01", "mission_id: M9")
    )
    assert run_mission(["--mission", str(other), "--run", str(run)]) == 1
    assert "is a run of mission 'M01', not 'M9'" in capsys.readouterr().err
    assert not (run / "readings.json").exists()


def test_a_run_that_flew_another_plan_is_refused(tmp_path, capsys):
    run = _kept_run(tmp_path / "run")
    (run / "mission.plan").write_text("{}\n")
    mission = _m01_mission(tmp_path / "m01")
    assert run_mission(["--mission", str(mission), "--run", str(run)]) == 1
    assert "the plan" in capsys.readouterr().err
    assert not (run / "readings.json").exists()


@pytest.mark.parametrize("kept_name", ["settings.yaml", "simple.yaml"])
def test_a_run_whose_kept_settings_differ_is_refused(tmp_path, capsys, kept_name):
    # The run kept a 12 s hold; the mission's settings, under another name, say 5 s.
    # The replay must verify the 12 s it flew with, not fall back to the 5 s file. A
    # run kept before the name was fixed has its settings under their own name.
    run = _kept_run(tmp_path / "run")
    (run / "settings.yaml").rename(run / kept_name)
    kept = run / kept_name
    kept.write_text(kept.read_text().replace("min_s: 5", "min_s: 12"))
    mission = _m01_mission(tmp_path / "m01")
    (mission / "simple.yaml").rename(mission / "other-name.yaml")
    assert run_mission(["--mission", str(mission), "--run", str(run)]) == 1
    err = capsys.readouterr().err
    assert f"{kept_name} isn't the mission's other-name.yaml" in err
    assert not (run / "readings.json").exists()


def test_a_run_is_read_with_the_config_it_kept(tmp_path):
    import run_mission as runner

    run = _kept_run(tmp_path / "run")
    assert runner.run_config(run, None) == run / "px4.yaml"
    assert runner.run_config(run, CONFIG) == run / "px4.yaml"  # the same bytes
    other = tmp_path / "other.yaml"
    other.write_text(CONFIG.read_text() + "# a different config\n")
    with pytest.raises(runner.StepError, match="its own px4.yaml"):
        runner.run_config(run, other)


def test_an_existing_verdict_is_not_written_over(tmp_path):
    run = _kept_run(tmp_path / "run")
    (run / "verdict.json").write_text('{"verdict": "kept"}\n')
    assert run_mission(["--run", str(run)]) == 1
    assert (run / "verdict.json").read_text() == '{"verdict": "kept"}\n'
    assert not (run / "readings.json").exists()


@pytest.mark.skipif(
    not os.environ.get("HYDRA_R02_ULG"), reason="set HYDRA_R02_ULG to R02.ulg"
)
def test_a_run_folder_replays_on_its_own(tmp_path):
    # Everything the run kept: its plan, states, settings and config, and the log.
    run = _kept_run(tmp_path / "run")
    shutil.copy(os.environ["HYDRA_R02_ULG"], run / "R02.ulg")
    assert run_mission(["--run", str(run)]) == 0
    got = json.loads((run / "verdict.json").read_text())
    want = json.loads((M01 / "R02" / "expected-verdict.json").read_text())
    assert got["verdict"] == want["verdict"] == "PASS"
    assert _checks(got) == _checks(want)


@pytest.mark.parametrize("form", ["child line", "agent tag"])
def test_the_generators_output_plans_in_both_vehicle_type_forms(tmp_path, form):
    # The generator keeps vehicle_type where the template puts it: a <vehicle_type>
    # element (the M01 fixture) or on the <agent> tag (#16's template). Both must plan.
    template = (M01 / "start.xml").read_text()
    if form == "agent tag":
        line = '    <vehicle_type type="string" value="multicopter"/>\n'
        assert line in template
        template = template.replace(line, "").replace(
            "<agent ", '<agent vehicle_type="" ', 1
        )
    path = tmp_path / "template.xml"
    path.write_text(template)
    result = generate(path, M01 / "simple.yaml", CONFIG, 7)  # asks the plan step too
    start = ET.tostring(result["start"].getroot(), encoding="unicode")
    assert ('vehicle_type="multicopter"' in start) == (form == "agent tag")
    settings = yaml.safe_load((M01 / "simple.yaml").read_text())
    plan = plan_mission(result["start"], result["goal"], settings, load_config())
    assert [item["command"] for item in plan["mission"]["items"]] == [22, 16, 20]


# ---- Replays with a missing plan, and both vehicle_type forms ------------------------


def test_a_replay_never_writes_a_missing_plan_into_the_run(tmp_path, capsys):
    # The run names a log, so it flew, but the plan it flew is gone. The replay must
    # refuse it, not rebuild the plan inside the run and compare it with itself.
    run = _kept_run(tmp_path / "run")
    (run / "mission.plan").unlink()
    assert run_mission(["--run", str(run)]) == 1
    assert "is missing" in capsys.readouterr().err
    for name in ("mission.plan", "readings.json", "verdict.json"):
        assert not (run / name).exists(), name


def _agent_tag(text):
    line = '    <vehicle_type type="string" value="multicopter"/>\n'
    assert line in text
    return text.replace(line, "").replace(
        "<agent ", '<agent vehicle_type="multicopter" ', 1
    )


def test_both_vehicle_type_forms_get_the_same_checks(tmp_path):
    # The same mission with vehicle_type as an element or on the <agent> tag. Both
    # must PASS: losing the vehicle type would FAIL the goal check.
    verdicts = []
    for form in ("line", "tag"):
        mission = _m01_mission(tmp_path / form)
        if form == "tag":
            for name in ("start.xml", "goal.xml"):
                (mission / name).write_text(_agent_tag((mission / name).read_text()))
        out = tmp_path / f"{form}.json"
        readings = M01 / "R02" / "readings.json"
        args = [str(mission), str(readings), "--config", str(CONFIG)]
        assert verify([*args, "--output", str(out)]) == 0
        verdicts.append(json.loads(out.read_text()))
    assert _checks(verdicts[0]) == _checks(verdicts[1])
    assert verdicts[1]["verdict"] == "PASS"


def test_a_mission_whose_settings_are_called_px4_yaml_still_plans(tmp_path):
    # Only a run folder keeps the config as px4.yaml; in a mission folder it's the
    # settings, whatever they're called.
    mission = tmp_path / "m01"
    mission.mkdir()
    for name in ("start.xml", "goal.xml"):
        shutil.copy(M01 / name, mission / name)
    shutil.copy(M01 / "simple.yaml", mission / "px4.yaml")
    assert run_mission(["--mission", str(mission)]) == 2  # planned, nothing flown
    assert (mission / "mission.plan").read_text() == (M01 / "mission.plan").read_text()


def test_a_listed_disarm_in_an_older_mission_yaml_is_checked_once(tmp_path):
    for name in ("start.xml", "goal.xml"):
        shutil.copy(M01 / name, tmp_path / name)
    (tmp_path / "mission.yaml").write_text(
        "mission_id: M01\nstart: start.xml\ngoal: goal.xml\npostconditions:\n"
        "  - hold_at: {waypoint: W1, min_s: 5}\n  - disarmed_after_landing: {}\n"
    )
    out = tmp_path / "verdict.json"
    readings = M01 / "R02" / "readings.json"
    args = [str(tmp_path / "mission.yaml"), str(readings), "--config", str(CONFIG)]
    assert verify([*args, "--output", str(out)]) == 0
    checks = [c["check"] for c in json.loads(out.read_text())["checks"]]
    assert checks.count("disarmed_after_landing") == 1
