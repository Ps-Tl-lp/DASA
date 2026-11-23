"""Tests for the log reader (log_reader/).

The runs here are small made-up flights written as real .ulg files (tests/_ulog.py),
with numbers chosen so every expected value can be worked out by hand. One more test
compares the M01 fixture's R02 readings with a fresh read of R02.ulg. It runs only where
that log is (set HYDRA_R02_ULG to its path), because raw logs stay out of git.
"""

import json
import os
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


def _run(folder, log_topics, recording_lines=None, **run_extra):
    """Write run.json, run.ulg and (if given) gz_pose.jsonl into folder."""
    folder.mkdir(parents=True, exist_ok=True)
    write_ulog(folder / "run.ulg", log_topics, {"TRIG_MODE": 0})
    run = {
        "mission_id": "T",
        "run_id": "R1",
        "run_status": "completed",
        "log": "run.ulg",
    }
    if recording_lines is not None:
        run["recording"] = "gz_pose.jsonl"
        if recording_lines != "absent":
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


def test_a_run_with_no_log_cant_be_read():
    with pytest.raises(ReaderError, match="no log"):
        read_run(M01)  # R01 is made up by hand: run.json's log is null


def test_a_log_without_the_time_zero_topics_cant_be_read(tmp_path):
    folder = _run(tmp_path, {"vehicle_status": LOG_ONLY_TOPICS["vehicle_status"]})
    with pytest.raises(ReaderError, match="none of"):
        read_run(folder)


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
    folder = _run(tmp_path, LOG_ONLY_TOPICS)
    assert main([str(folder)]) == 0
    assert (
        json.loads((folder / "readings.json").read_text())["time_zero_us"] == 1_000_000
    )


def test_command_line_says_why_a_run_cant_be_read(capsys):
    assert main([str(M01), "--out", os.devnull]) == 1
    assert "can't read the run" in capsys.readouterr().err


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
        # The fixture subtracted in 32-bit floats; we subtract in 64-bit. Two of 1300 z
        # values round the other way in the 4th decimal, so allow one unit there.
        assert [r["t_s"] for r in readings[key]] == [r["t_s"] for r in value]
        for ours, theirs in zip(readings[key], value, strict=True):
            for axis in "xyz":
                assert ours[axis] == pytest.approx(theirs[axis], abs=1.01e-4), (
                    key,
                    ours,
                )
