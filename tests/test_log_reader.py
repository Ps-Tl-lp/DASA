"""Tests for the log reader (log_reader/).

The runs here are small made-up flights written as real .ulg files (tests/_ulog.py),
with numbers chosen so every expected value can be worked out by hand. One more test
compares the M01 fixture's R02 readings with a fresh read of R02.ulg. It runs only where
that log is (set HYDRA_R02_ULG to its path), because raw logs stay out of git.
"""

import json
import os
import shutil
from pathlib import Path

import pytest
from _ulog import write_ulog

from log_reader import ReaderError, landed, rate_of, read_run, readings_text
from log_reader.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
M01 = ROOT / "tests" / "fixtures" / "m01"

GT = [
    ("uint64_t", "timestamp"),
    ("float", "x"),
    ("float", "y"),
    ("float", "z"),
    ("float", "vx"),
    ("float", "vy"),
    ("float", "vz"),
]
LAND = [("uint64_t", "timestamp"), ("bool", "landed")]
STATUS = [
    ("uint64_t", "timestamp"),
    ("uint8_t", "nav_state"),
    ("uint8_t", "latest_disarming_reason"),
    ("uint8_t", "arming_state"),
]


def _run(
    folder,
    log_topics,
    recording_lines=None,
    parameters=None,
    damaged=False,
    **run_extra,
):
    """Write run.json, run.ulg and (if given) gz_pose.jsonl into folder.

    recording_lines: a list of JSON objects, raw text, or "absent" (named, not written).
    """
    folder.mkdir(parents=True, exist_ok=True)
    write_ulog(
        folder / "run.ulg",
        log_topics,
        {"TRIG_MODE": 0} if parameters is None else parameters,
        damaged,
    )
    run = {
        "mission_id": "T",
        "run_id": "R1",
        "run_status": "completed",
        "log": "run.ulg",
    }
    if recording_lines is not None:
        run["recording"] = "gz_pose.jsonl"
        if isinstance(recording_lines, str) and recording_lines != "absent":
            (folder / "gz_pose.jsonl").write_text(recording_lines)
        elif recording_lines != "absent":
            lines = "\n".join(json.dumps(line) for line in recording_lines)
            (folder / "gz_pose.jsonl").write_text(lines + "\n")
    run.update(run_extra)
    (folder / "run.json").write_text(json.dumps(run))
    return folder


# ---- A run read from the log alone ---------------------------------------------------
# Time zero is the first landed sample, at 1.0 s. Positions are 0.1 s apart from 1.1 s.
# The log's world position is x 10 -> 13 north, y 5 -> 4 east, z -2 -> -6 (down).

LOG_ONLY_TOPICS = {
    "vehicle_local_position_groundtruth": (
        GT,
        [
            (1_100_000, 10.0, 5.0, -2.0, 0.0, 0.0, 0.0),
            (1_200_000, 10.0, 5.0, -2.0, 0.0, 0.0, 0.0),
            (1_300_000, 11.0, 5.0, -4.0, 10.0, 0.0, -20.0),
            (1_400_000, 13.0, 4.0, -6.0, 20.0, -10.0, -20.0),
        ],
    ),
    "vehicle_land_detected": (LAND, [(1_000_000, True), (1_350_000, False)]),
    "vehicle_status": (STATUS, [(1_050_000, 4, 0, 1), (1_250_000, 3, 0, 2)]),
}


def test_a_log_only_run_reads_every_sample_measured_from_the_first(tmp_path):
    readings = read_run(_run(tmp_path, LOG_ONLY_TOPICS))
    assert readings == {
        "mission_id": "T",
        "run_id": "R1",
        "run_status": "completed",
        # x - 10, y - 5, and z flipped to up: -(z - -2)
        "position": [
            {"t_s": 0.1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"t_s": 0.2, "x": 0.0, "y": 0.0, "z": 0.0},
            {"t_s": 0.3, "x": 1.0, "y": 0.0, "z": 2.0},
            {"t_s": 0.4, "x": 3.0, "y": -1.0, "z": 4.0},
        ],
        # the log's own velocity, vz flipped to up
        "velocity": [
            {"t_s": 0.1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"t_s": 0.2, "x": 0.0, "y": 0.0, "z": 0.0},
            {"t_s": 0.3, "x": 10.0, "y": 0.0, "z": 20.0},
            {"t_s": 0.4, "x": 20.0, "y": -10.0, "z": 20.0},
        ],
        "landed": [{"t_s": 0.0, "value": True}, {"t_s": 0.35, "value": False}],
        "nav_state": [{"t_s": 0.05, "value": 4}, {"t_s": 0.25, "value": 3}],
        "disarm_reason": [{"t_s": 0.05, "value": 0}, {"t_s": 0.25, "value": 0}],
        "arming_state": [{"t_s": 0.05, "value": 1}, {"t_s": 0.25, "value": 2}],
        "camera_triggered_at": [],
        "camera_trigger_mode": 0,
        "missing_topics": ["camera_capture"],
        "sources": "log only",
        "time_zero_us": 1_000_000,
    }


def test_a_run_status_and_reason_are_copied_from_run_json(tmp_path):
    folder = _run(
        tmp_path, LOG_ONLY_TOPICS, run_status="inconclusive", reason="timeout"
    )
    readings = read_run(folder)
    assert (readings["run_status"], readings["reason"]) == ("inconclusive", "timeout")


def test_a_run_with_no_log_reads_as_no_readings_and_says_why(tmp_path):
    # Decided: a run with no flight log is INCONCLUSIVE. There is nothing to read, so
    # the readings are empty, every log topic is missing, and log_problem says why.
    folder = tmp_path / "run"
    folder.mkdir()
    setup = {"px4_commit": "fca3df865a", "simulator": "gz", "speed": 4}
    run = {
        "mission_id": "T",
        "run_id": "R9",
        "run_status": "inconclusive",
        "reason": "sim_setup",
        "log": None,
        "recording": "gz_pose.jsonl",
        "record": setup,
    }
    (folder / "run.json").write_text(json.dumps(run))
    readings = read_run(folder)
    assert (readings["run_status"], readings["reason"]) == ("inconclusive", "sim_setup")
    assert readings["record"] == setup
    assert "no flight log" in readings["log_problem"]
    assert readings["position"] == readings["velocity"] == readings["nav_state"] == []
    assert "vehicle_status" in readings["missing_topics"]
    assert readings["cross_check"]["verdict"] == "INCONCLUSIVE"
    assert "no flight log" in readings["cross_check"]["reason"]
    assert "time_zero_us" not in readings  # no log, no PX4 clock to measure from


def test_a_log_only_run_with_no_log_reads_the_same_way():
    readings = read_run(M01)  # R01 is made up by hand: run.json's log is null
    assert "no flight log" in readings["log_problem"]
    assert readings["position"] == []
    assert "cross_check" not in readings


def test_a_log_without_the_time_zero_topics_reads_as_inconclusive(tmp_path):
    # Nothing in it can be timed, so its evidence is missing: like a run with no log.
    folder = _run(tmp_path, {"vehicle_status": LOG_ONLY_TOPICS["vehicle_status"]})
    readings = read_run(folder)
    assert "none of" in readings["log_problem"]
    assert readings["position"] == [] and readings["nav_state"] == []


# ---- A recorded run ------------------------------------------------------------------
# Time zero is the first landed sample, at 1.95 s. The log's ground truth runs 2.0 to
# 2.3 s. Gazebo's recording (east, north, up) runs 1.9 to 2.4 s and agrees with the log
# where both exist: north 3 -> 6, east 1, up 0.5 -> 4.5. The log's z is down, so it runs
# -0.5 -> -4.5.

GT_ROWS = [
    (2_000_000, 3.0, 1.0, -0.5, 0.0, 0.0, 0.0),
    (2_100_000, 3.0, 1.0, -0.5, 0.0, 0.0, 0.0),
    (2_200_000, 4.0, 1.0, -2.5, 0.0, 0.0, 0.0),
    (2_300_000, 6.0, 1.0, -4.5, 0.0, 0.0, 0.0),
]
POSES = [
    (1.9, [1.0, 3.0, 0.5]),
    (2.0, [1.0, 3.0, 0.5]),
    (2.1, [1.0, 3.0, 0.5]),
    (2.2, [1.0, 4.0, 2.5]),
    (2.3, [1.0, 6.0, 4.5]),
    (2.4, [1.0, 7.0, 6.5]),
]
ONE_PUBLISHER = {"k": "pubs", "pubs": [["tcp://127.0.0.1:1", "gz.msgs.Pose_V"]]}


def _recorded_topics(gt_rows=GT_ROWS):
    return {
        "vehicle_local_position_groundtruth": (GT, gt_rows),
        "vehicle_land_detected": (LAND, [(1_950_000, True)]),
        "vehicle_status": (STATUS, [(2_000_000, 4, 0, 2)]),
    }


def _recording(poses=POSES, pubs=ONE_PUBLISHER, extra=()):
    lines = [{"k": "info", "topic": "/world/default/pose/info"}, pubs, *extra]
    return lines + [{"k": "pose", "t": t, "p": p} for t, p in poses]


def test_a_recorded_run_reads_position_from_gazebo_inside_the_logs_span(tmp_path):
    readings = read_run(_run(tmp_path, _recorded_topics(), _recording()))
    # 1.9 s and 2.4 s are outside the log's span and left out. Measured from 2.0 s.
    assert readings["position"] == [
        {"t_s": 0.05, "x": 0.0, "y": 0.0, "z": 0.0},
        {"t_s": 0.15, "x": 0.0, "y": 0.0, "z": 0.0},
        {"t_s": 0.25, "x": 1.0, "y": 0.0, "z": 2.0},
        {"t_s": 0.35, "x": 3.0, "y": 0.0, "z": 4.0},
    ]
    # change since the reading before, over 0.1 s; 0 for the first
    assert readings["velocity"] == [
        {"t_s": 0.05, "x": 0.0, "y": 0.0, "z": 0.0},
        {"t_s": 0.15, "x": 0.0, "y": 0.0, "z": 0.0},
        {"t_s": 0.25, "x": 10.0, "y": 0.0, "z": 20.0},
        {"t_s": 0.35, "x": 20.0, "y": 0.0, "z": 20.0},
    ]
    # on the ground (up <= 0.1 m) and still (< 0.1 m/s) for the first two only
    assert [r["value"] for r in readings["landed"]] == [True, True, False, False]
    assert readings["nav_state"] == [{"t_s": 0.05, "value": 4}]
    assert readings["time_zero_us"] == 1_950_000
    assert readings["sources"]["agent.x"] == "gz_pose"
    assert readings["sources"]["nav_state"] == "log"


def test_a_matching_recording_passes_the_cross_check(tmp_path):
    readings = read_run(_run(tmp_path, _recorded_topics(), _recording()))
    check = readings["cross_check"]
    assert {k: check[k] for k in check if k != "reason"} == {
        "recording": "gz_pose.jsonl",
        "compared": 4,
        "unmatched": 0,
        "over_limit": 0,
        "max_difference_m": 0.0,
        "publishers": 1,
        "verdict": "PASS",
    }


def test_an_edited_log_fails_the_cross_check_but_not_the_readings(tmp_path):
    edited = list(GT_ROWS)
    edited[2] = (2_200_000, 4.5, 1.0, -2.5, 0.0, 0.0, 0.0)  # 0.5 m further north
    readings = read_run(_run(tmp_path, _recorded_topics(edited), _recording()))
    check = readings["cross_check"]
    assert (check["verdict"], check["over_limit"], check["max_difference_m"]) == (
        "INCONCLUSIVE",
        1,
        0.5,
    )
    assert readings["position"][2]["x"] == 1.0  # still Gazebo's, not the log's


def test_a_recording_that_stops_early_is_inconclusive(tmp_path):
    short = [pose for pose in POSES if pose[0] <= 2.2]
    check = read_run(_run(tmp_path, _recorded_topics(), _recording(short)))[
        "cross_check"
    ]
    assert (check["verdict"], check["compared"], check["unmatched"]) == (
        "INCONCLUSIVE",
        3,
        1,
    )
    assert "1 of 4" in check["reason"]


def test_a_named_recording_that_is_missing_is_inconclusive_with_no_positions(tmp_path):
    readings = read_run(_run(tmp_path, _recorded_topics(), "absent"))
    check = readings["cross_check"]
    assert (check["verdict"], check["unmatched"]) == ("INCONCLUSIVE", 4)
    assert "missing" in check["reason"]
    assert readings["position"] == readings["velocity"] == readings["landed"] == []


def test_a_second_publisher_on_the_pose_topic_is_inconclusive(tmp_path):
    two = {
        "k": "pubs",
        "pubs": [["tcp://a", "gz.msgs.Pose_V"], ["tcp://b", "gz.msgs.Pose_V"]],
    }
    check = read_run(_run(tmp_path, _recorded_topics(), _recording(pubs=two)))[
        "cross_check"
    ]
    assert (check["verdict"], check["publishers"]) == ("INCONCLUSIVE", 2)


def test_a_recorder_error_is_inconclusive(tmp_path):
    error = {"k": "info", "error": "no model named x500*"}
    folder = _run(tmp_path, _recorded_topics(), _recording(extra=[error]))
    check = read_run(folder)["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "no model" in check["reason"]


# ---- The two worked-out readings -----------------------------------------------------


def test_rate_of_is_the_change_since_the_reading_before():
    series = [(0, 0.0), (500_000, 1.0), (1_000_000, 0.5)]  # times in microseconds
    assert rate_of(series) == [(0, 0.0), (500_000, 2.0), (1_000_000, -1.0)]


def test_landed_needs_both_low_and_still():
    height = [(0, 0.0), (1, 0.1), (2, 0.11), (3, 0.0)]
    speeds = [[(0, 0.0), (1, 0.0), (2, 0.0), (3, 0.1)], [(t, 0.0) for t in range(4)]]
    # 0.1 m is still on the ground (no higher than); 0.1 m/s is not still (below)
    assert landed(height, speeds, 0.1, 0.1) == [
        (0, True),
        (1, True),
        (2, False),
        (3, False),
    ]


# ---- readings.json's layout and the command line -------------------------------------


def test_readings_text_has_one_line_per_timed_value_and_round_trips(tmp_path):
    readings = read_run(_run(tmp_path, LOG_ONLY_TOPICS))
    text = readings_text(readings)
    assert json.loads(text) == readings
    assert '    {"t_s": 0.3, "x": 1.0, "y": 0.0, "z": 2.0},\n' in text
    assert text.endswith("}\n")


def test_command_line_writes_readings_json(tmp_path, capsys):
    folder = _run(tmp_path, LOG_ONLY_TOPICS, record={"speed": 4, "seed": 42})
    assert main([str(folder)]) == 0
    output = json.loads((folder / "readings.json").read_text())
    assert output["record"] == {"speed": 4}
    assert output["time_zero_us"] == 1_000_000


def test_command_line_says_why_a_run_cant_be_read(tmp_path, capsys):
    assert main([str(tmp_path), "--out", os.devnull]) == 1  # no run.json at all
    assert "can't read the run" in capsys.readouterr().err


def test_command_line_says_when_a_run_has_no_log(capsys):
    assert main([str(M01), "--out", os.devnull]) == 0
    assert "no flight log" in capsys.readouterr().out


# ---- The M01 fixture's real flight ---------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("HYDRA_R02_ULG"), reason="set HYDRA_R02_ULG to R02.ulg"
)
def test_r02_reads_as_the_fixture_says(tmp_path):
    (tmp_path / "run.json").write_text((M01 / "R02" / "run.json").read_text())
    (tmp_path / "R02.ulg").symlink_to(os.environ["HYDRA_R02_ULG"])
    readings = read_run(tmp_path)
    expected = json.loads((M01 / "R02" / "readings.json").read_text())
    assert list(readings) == list(expected)
    for key, value in expected.items():
        if key not in ("position", "velocity"):
            assert readings[key] == value, key
            continue
        if key == "velocity":
            assert readings[key] == value  # PX4's own, nothing subtracted
            continue
        # The fixture subtracted in 32-bit floats; we subtract in 64-bit. Two of 1300 z
        # values round the other way in the 4th decimal, so allow one unit there.
        assert [r["t_s"] for r in readings[key]] == [r["t_s"] for r in value]
        for ours, theirs in zip(readings[key], value, strict=True):
            for axis in "xyz":
                assert ours[axis] == pytest.approx(theirs[axis], abs=1.01e-4), (
                    key,
                    ours,
                )


# ---- Runs that go wrong in smaller ways ---------------------------------------------


def test_a_null_recording_is_a_recorded_run_with_no_file(tmp_path):
    folder = _run(tmp_path, _recorded_topics(), "absent", recording=None)
    readings = read_run(folder)
    assert readings["cross_check"]["verdict"] == "INCONCLUSIVE"
    assert "no recording" in readings["cross_check"]["reason"]
    assert readings["position"] == []


def test_nan_in_the_log_is_never_within_the_limit(tmp_path):
    rows = list(GT_ROWS)
    rows[1] = (2_100_000, float("nan"), 1.0, -0.5, 0.0, 0.0, 0.0)
    check = read_run(_run(tmp_path, _recorded_topics(rows), _recording()))[
        "cross_check"
    ]
    assert (check["verdict"], check["over_limit"]) == ("INCONCLUSIVE", 1)


def test_nan_in_a_log_only_run_is_written_as_null(tmp_path):
    topics = dict(LOG_ONLY_TOPICS)
    fields, rows = topics["vehicle_local_position_groundtruth"]
    rows = [rows[0], (1_200_000, float("nan"), 5.0, -2.0, 0, 0, 0), *rows[2:]]
    topics["vehicle_local_position_groundtruth"] = (fields, rows)
    readings = read_run(_run(tmp_path, topics))
    assert readings["position"][1]["x"] is None
    assert json.loads(readings_text(readings))["position"][1]["x"] is None


def test_a_second_publisher_that_comes_and_goes_is_inconclusive(tmp_path):
    two = {"k": "pubs", "pubs": [["tcp://a", "T"], ["tcp://b", "T"]]}
    one_again = {"k": "pubs", "pubs": [["tcp://a", "T"]]}
    first = {"k": "pubs", "pubs": [["tcp://a", "T"]]}
    lines = _recording(pubs=first, extra=[two, one_again])
    check = read_run(_run(tmp_path, _recorded_topics(), lines))["cross_check"]
    assert (check["verdict"], check["publishers"]) == ("INCONCLUSIVE", 2)


def test_a_publisher_lookup_that_failed_is_inconclusive_but_keeps_the_poses(tmp_path):
    failed = {"k": "pubs", "pubs": [["error", "TimeoutError()"]]}
    readings = read_run(_run(tmp_path, _recorded_topics(), _recording(extra=[failed])))
    check = readings["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "ruled out" in check["reason"]
    assert (check["compared"], check["unmatched"], check["publishers"]) == (4, 0, 1)
    assert len(readings["position"]) == 4


def test_a_recording_that_never_lists_publishers_says_so(tmp_path):
    lines = [line for line in _recording() if line.get("k") != "pubs"]
    check = read_run(_run(tmp_path, _recorded_topics(), lines))["cross_check"]
    assert (check["verdict"], check["publishers"]) == ("INCONCLUSIVE", None)
    assert "never listed" in check["reason"]


def test_a_recording_that_starts_after_the_log_gives_no_positions(tmp_path):
    late = [pose for pose in POSES if pose[0] >= 2.2]
    readings = read_run(_run(tmp_path, _recorded_topics(), _recording(late)))
    # No recorded sample at the log's first ground-truth sample (2.0 s): no origin.
    assert readings["position"] == readings["velocity"] == readings["landed"] == []
    check = readings["cross_check"]
    assert (check["verdict"], check["unmatched"]) == ("INCONCLUSIVE", 2)


def test_recording_lines_out_of_order_or_repeated_read_the_same(tmp_path):
    shuffled = [POSES[3], POSES[0], POSES[5], POSES[1], POSES[4], POSES[2]]
    repeat = POSES[2]  # the same sim time and pose again, later in the file
    ordered = read_run(_run(tmp_path / "a", _recorded_topics(), _recording()))
    jumbled = read_run(
        _run(tmp_path / "b", _recorded_topics(), _recording([*shuffled, repeat]))
    )
    assert jumbled["position"] == ordered["position"]
    assert jumbled["cross_check"]["verdict"] == "PASS"


def test_a_cut_off_last_line_is_ignored_but_a_bad_line_inside_is_not(tmp_path):
    whole = "\n".join(json.dumps(line) for line in _recording()) + "\n"
    torn = whole + '{"k": "pose", "t": 2.5, "p": [1.0,'
    inside = whole.replace('{"k": "pose", "t": 2.2', 'garbage\n{"k": "pose", "t": 2.2')
    assert (
        read_run(_run(tmp_path / "a", _recorded_topics(), torn))["cross_check"][
            "verdict"
        ]
        == "PASS"
    )
    check = read_run(_run(tmp_path / "b", _recorded_topics(), inside))["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "isn't JSON" in check["reason"]


def test_a_parameter_the_log_didnt_record_is_null(tmp_path):
    readings = read_run(_run(tmp_path, LOG_ONLY_TOPICS, parameters={}))
    assert readings["camera_trigger_mode"] is None


def test_camera_triggers_are_listed_as_times(tmp_path):
    topics = dict(LOG_ONLY_TOPICS)
    topics["camera_capture"] = (
        [("uint64_t", "timestamp")],
        [(1_250_000,), (1_300_000,)],
    )
    readings = read_run(_run(tmp_path, topics, parameters={"TRIG_MODE": 1}))
    assert readings["camera_triggered_at"] == [{"t_s": 0.25}, {"t_s": 0.3}]
    assert readings["camera_trigger_mode"] == 1
    assert readings["missing_topics"] == []


def test_a_recorded_run_without_ground_truth_lists_it_as_missing(tmp_path):
    topics = _recorded_topics()
    del topics["vehicle_local_position_groundtruth"]
    readings = read_run(_run(tmp_path, topics, _recording()))
    assert "vehicle_local_position_groundtruth" in readings["missing_topics"]
    assert readings["position"] == []
    assert readings["cross_check"]["verdict"] == "INCONCLUSIVE"


def test_a_field_the_config_names_but_the_log_lacks_cant_be_read(tmp_path):
    topics = dict(LOG_ONLY_TOPICS)
    topics["vehicle_status"] = (STATUS[:3], [(1_050_000, 4, 0)])  # no arming_state
    with pytest.raises(ReaderError, match="arming_state"):
        read_run(_run(tmp_path, topics))


def test_a_log_that_is_nan_throughout_has_no_largest_difference(tmp_path):
    nan = float("nan")
    rows = [(t, nan, nan, nan, 0.0, 0.0, 0.0) for t, *_ in GT_ROWS]
    check = read_run(_run(tmp_path, _recorded_topics(rows), _recording()))[
        "cross_check"
    ]
    assert (check["over_limit"], check["max_difference_m"]) == (4, None)


def test_a_bad_line_is_named_by_its_line_number_in_the_file(tmp_path):
    lines = [json.dumps(line) for line in _recording()]
    text = "\n".join([lines[0], "", "", "garbage", *lines[1:]]) + "\n"
    check = read_run(_run(tmp_path, _recorded_topics(), text))["cross_check"]
    assert "line 4 " in check["reason"]


def test_a_publisher_line_that_isnt_a_list_of_pairs_is_inconclusive(tmp_path):
    odd = {"k": "pubs", "pubs": [{"address": "tcp://a"}]}
    check = read_run(_run(tmp_path, _recorded_topics(), _recording(pubs=odd)))[
        "cross_check"
    ]
    assert check["verdict"] == "INCONCLUSIVE" and "publisher list" in check["reason"]


# ---- A damaged log, and a recording with two poses at once ---------------------------


def test_a_damaged_log_is_reported_and_its_cross_check_is_inconclusive(tmp_path):
    clean = read_run(_run(tmp_path / "clean", _recorded_topics(), _recording()))
    damaged = read_run(
        _run(tmp_path / "damaged", _recorded_topics(), _recording(), damaged=True)
    )
    assert "log_problem" not in clean
    assert clean["cross_check"]["verdict"] == "PASS"
    # pyulog skips the damaged part. What is left still agrees with the recording, so
    # only the reader's report shows the damage (R5: a corrupted log is INCONCLUSIVE).
    assert "damaged" in damaged["log_problem"]
    check = damaged["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "damaged" in check["reason"]
    assert (check["compared"], check["unmatched"], check["over_limit"]) == (3, 0, 0)


def test_a_damaged_log_only_run_is_reported(tmp_path):
    readings = read_run(_run(tmp_path, LOG_ONLY_TOPICS, damaged=True))
    assert "damaged" in readings["log_problem"]
    assert "cross_check" not in readings


def test_two_different_poses_at_one_time_are_inconclusive(tmp_path):
    second = (2.1, [1.0, 4.0, 0.5])  # 1 m further north, at a time already recorded
    readings = read_run(
        _run(tmp_path, _recorded_topics(), _recording([*POSES, second]))
    )
    check = readings["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "2.1" in check["reason"]
    assert readings["position"] == []


# ---- Records written wrong, torn lines, and logs that can't be read ------------------


def test_the_command_line_wont_write_over_existing_readings(tmp_path):
    # R01's readings were made by hand; it has no log to read them again from.
    folder = tmp_path / "m01"
    shutil.copytree(M01, folder)
    before = (folder / "readings.json").read_bytes()
    assert main([str(folder)]) == 1
    assert (folder / "readings.json").read_bytes() == before
    assert main([str(folder), "--replace"]) == 0
    assert (folder / "readings.json").read_bytes() != before


@pytest.mark.parametrize("value", [False, 0, [], "", "   "])
def test_a_log_that_isnt_a_file_name_or_null_cant_be_read(tmp_path, value):
    folder = _run(tmp_path, LOG_ONLY_TOPICS, log=value)
    with pytest.raises(ReaderError, match="file name or null"):
        read_run(folder)


def test_a_run_json_with_no_log_field_cant_be_read(tmp_path):
    folder = _run(tmp_path, LOG_ONLY_TOPICS)
    run = json.loads((folder / "run.json").read_text())
    del run["log"]
    (folder / "run.json").write_text(json.dumps(run))
    with pytest.raises(ReaderError, match="file name or null"):
        read_run(folder)


def test_a_complete_but_broken_last_line_is_inconclusive(tmp_path):
    # A last line that ends in a newline was written whole, so it wasn't cut off by
    # the recorder stopping: it is damage, not a torn write.
    lines = "\n".join(json.dumps(line) for line in _recording())
    text = lines + '\n{"k": "pubs", "pubs": [[\n'
    readings = read_run(_run(tmp_path, _recorded_topics(), text))
    check = readings["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "isn't JSON" in check["reason"]


def test_a_recording_that_isnt_utf8_is_inconclusive(tmp_path):
    folder = _run(tmp_path, _recorded_topics(), _recording())
    with open(folder / "gz_pose.jsonl", "ab") as stream:
        stream.write(b'{"k": "info", "note": "\xff\xfe"}\n')
    check = read_run(folder)["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "UTF-8" in check["reason"]


def test_a_publisher_entry_without_its_type_is_inconclusive(tmp_path):
    pubs = {"k": "pubs", "pubs": [["tcp://127.0.0.1:1"]]}  # an address, no type
    readings = read_run(_run(tmp_path, _recorded_topics(), _recording(pubs=pubs)))
    check = readings["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "publisher list" in check["reason"]


@pytest.mark.parametrize("recorded", [False, True], ids=["log only", "recorded"])
def test_a_log_pyulog_cant_open_reads_as_inconclusive(tmp_path, recorded):
    folder = _run(tmp_path, LOG_ONLY_TOPICS, _recording() if recorded else None)
    (folder / "run.ulg").write_bytes(b"this is not a ULog file at all")
    readings = read_run(folder)
    assert "can't be read" in readings["log_problem"]
    assert readings["position"] == []
    if recorded:
        assert readings["cross_check"]["verdict"] == "INCONCLUSIVE"
    else:
        assert "cross_check" not in readings


def test_a_log_cut_off_before_its_first_sample_reads_as_inconclusive(tmp_path):
    # Cut off partway through its definitions, the log has no topics left. pyulog
    # flags only some cuts like this as damage, so the reader can't rely on that
    # flag: either way nothing can be timed, so it's INCONCLUSIVE (R5).
    folder = _run(tmp_path, LOG_ONLY_TOPICS)
    data = (folder / "run.ulg").read_bytes()
    (folder / "run.ulg").write_bytes(data[: len(data) // 2])
    readings = read_run(folder)
    assert "can be timed" in readings["log_problem"]
    assert readings["position"] == []


# ---- More broken recordings, and readings written meanwhile --------------------------


def test_a_broken_line_with_its_newline_is_damage_even_with_spaces_after(tmp_path):
    # Only the final line, with no newline after it, can be an unfinished write.
    lines = "\n".join(json.dumps(line) for line in _recording())
    text = lines + '\n{"k": "pubs", "pubs": [[\n  '
    check = read_run(_run(tmp_path, _recorded_topics(), text))["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "isn't JSON" in check["reason"]


def test_a_recording_that_cant_be_opened_is_inconclusive_and_keeps_the_log(tmp_path):
    folder = _run(tmp_path, _recorded_topics(), _recording())
    os.chmod(folder / "gz_pose.jsonl", 0)
    try:
        readings = read_run(folder)
    finally:
        os.chmod(folder / "gz_pose.jsonl", 0o644)
    check = readings["cross_check"]
    assert check["verdict"] == "INCONCLUSIVE" and "can't be read" in check["reason"]
    assert readings["nav_state"]  # the log's own readings are kept


def test_a_publisher_line_that_isnt_a_list_is_inconclusive_after_a_good_one(tmp_path):
    bad = {"k": "pubs", "pubs": False}
    folder = _run(tmp_path, _recorded_topics(), _recording(extra=[bad]))
    assert read_run(folder)["cross_check"]["verdict"] == "INCONCLUSIVE"


def test_readings_that_appear_while_reading_are_not_written_over(tmp_path, monkeypatch):
    import log_reader.__main__ as cli

    folder = _run(tmp_path, LOG_ONLY_TOPICS)
    out = folder / "readings.json"
    real = cli.read_run

    def read_then_someone_writes(*args, **kwargs):
        readings = real(*args, **kwargs)
        out.write_text("written meanwhile\n")
        return readings

    monkeypatch.setattr(cli, "read_run", read_then_someone_writes)
    assert main([str(folder)]) == 1
    assert out.read_text() == "written meanwhile\n"
