"""Readable, synthetic examples of the verifier's documented rules.

Distances are metres; timestamps are simulation seconds. These are deliberately
small readings, not claims about a real flight. Expected answers are constructed
from docs/testing.md and platform_configs/px4.yaml, never copied from verify().
"""

from dataclasses import replace
from pathlib import Path

import pytest

from verifier.checks import (
    check_clicked_pic,
    check_disarmed_after_landing,
    check_goal,
    check_visited,
)
from verifier.checks.postconditions import (
    check_hold_at,
    check_stays_in_geofence,
    check_visits_in_order,
)
from verifier.config import load_config
from verifier.engine import verify
from verifier.loaders import load_mission
from verifier.models import CrossCheckData, Readings, TimedBool, TimedInt, TimedVec3
from verifier.validation import VerifierInputError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def config():
    return load_config(ROOT / "platform_configs" / "px4.yaml")


@pytest.fixture
def mission_states():
    # M01 asks for W1 at (50, 0, 20), a five-second hold and a return to base.
    return load_mission(ROOT / "tests" / "fixtures" / "m01")


@pytest.fixture
def flight():
    """Visit W1, land at base at 0.2 s, then disarm at 0.3 s.

    This short trace satisfies visits/goal/disarm, but NOT M01's five-second hold.
    PX4 enum values: mission=3, armed=2, disarmed=1, landing disarm reason=6.
    """
    return Readings(
        mission_id="M01",
        run_id="synthetic",
        run_status="completed",
        reason=None,
        position=(TimedVec3(0, 50, 0, 20), TimedVec3(0.1, 0, 0, 0)),
        velocity=(TimedVec3(0.3, 0, 0, 0),),
        landed=(TimedBool(0, False), TimedBool(0.2, True)),
        nav_state=(TimedInt(0, 3),),
        arming_state=(TimedInt(0, 2), TimedInt(0.3, 1)),
        disarm_reason=(TimedInt(0.3, 6),),
    )


def test_visit_at_the_horizontal_boundary_counts(mission_states, flight, config):
    _, start, goal = mission_states
    waypoint = goal.waypoints["W1"]
    edge = TimedVec3(0, waypoint.x + config.at_waypoint.within_m, 0, 20)
    readings = replace(flight, position=(edge,))

    result = check_visited(waypoint, start.waypoints["W1"], readings, config)

    assert result.verdict == "PASS"


def test_landed_without_visiting_is_a_failure(mission_states, flight, config):
    _, start, goal = mission_states
    # A complete trace at base cannot contain a visit to W1, 50 metres away.
    readings = replace(flight, position=(TimedVec3(0, 0, 0, 0),))
    result = check_visited(
        goal.waypoints["W1"], start.waypoints["W1"], readings, config
    )
    assert result.verdict == "FAIL"


def test_gap_could_hide_a_visit(mission_states, flight, config):
    _, start, goal = mission_states
    readings = replace(
        flight,
        position=(TimedVec3(0, 0, 0, 0), TimedVec3(1, 0, 0, 0)),
    )
    result = check_visited(
        goal.waypoints["W1"], start.waypoints["W1"], readings, config
    )
    assert result.verdict == "INCONCLUSIVE"


@pytest.mark.parametrize("offset, expected", [(0, "PASS"), (0.01, "FAIL")])
def test_visit_height_boundary(mission_states, flight, config, offset, expected):
    _, start, goal = mission_states
    height = 20 + config.at_waypoint.height_within_m + offset
    readings = replace(flight, position=(TimedVec3(0, 50, 0, height),))
    result = check_visited(
        goal.waypoints["W1"], start.waypoints["W1"], readings, config
    )
    assert result.verdict == expected


@pytest.mark.parametrize("extra, expected", [(0, "PASS"), (0.01, "FAIL")])
def test_final_position_boundary(mission_states, flight, config, extra, expected):
    _, start, goal = mission_states
    readings = replace(
        flight,
        position=(TimedVec3(0.3, config.goal_check.max_distance_m + extra, 0, 0),),
    )
    assert check_goal(start, goal, readings, config).verdict == expected


@pytest.mark.parametrize("extra, expected", [(0, "PASS"), (0.01, "FAIL")])
def test_final_speed_boundary(mission_states, flight, config, extra, expected):
    _, start, goal = mission_states
    readings = replace(
        flight,
        velocity=(TimedVec3(0.3, config.goal_check.max_speed_m_s + extra, 0, 0),),
    )
    assert check_goal(start, goal, readings, config).verdict == expected


def test_missing_velocity_cannot_prove_the_goal(mission_states, flight, config):
    _, start, goal = mission_states
    readings = replace(flight, velocity=())
    assert check_goal(start, goal, readings, config).verdict == "INCONCLUSIVE"


def test_disarm_after_touchdown_passes(flight, config):
    assert check_disarmed_after_landing(flight, config).verdict == "PASS"


def test_disarm_before_touchdown_fails(flight, config):
    readings = replace(flight, arming_state=(TimedInt(0, 2), TimedInt(0.1, 1)))
    assert check_disarmed_after_landing(readings, config).verdict == "FAIL"


def test_wrong_disarm_reason_fails(flight, config):
    readings = replace(flight, disarm_reason=(TimedInt(0.3, 1),))
    assert check_disarmed_after_landing(readings, config).verdict == "FAIL"


def test_disarm_reason_from_the_future_is_not_evidence(flight, config):
    readings = replace(flight, disarm_reason=(TimedInt(0.4, 6),))
    assert check_disarmed_after_landing(readings, config).verdict == "INCONCLUSIVE"


def test_landing_without_a_disarm_is_inconclusive(flight, config):
    readings = replace(flight, arming_state=(TimedInt(0, 2),))
    assert check_disarmed_after_landing(readings, config).verdict == "INCONCLUSIVE"


def test_rearming_after_landing_fails(flight, config):
    readings = replace(flight, arming_state=(*flight.arming_state, TimedInt(0.4, 2)))
    assert check_disarmed_after_landing(readings, config).verdict == "FAIL"


@pytest.mark.parametrize("duration, expected", [(4.75, "PASS"), (4.70, "FAIL")])
def test_five_second_hold_allows_only_configured_shortfall(
    mission_states, flight, config, duration, expected
):
    _, _, goal = mission_states
    # Config permits 0.25 s shortfall. Samples every 0.05 s avoid log gaps.
    positions = tuple(TimedVec3(i / 20, 50, 0, 20) for i in range(round(duration * 20)))
    readings = replace(flight, position=(*positions, TimedVec3(duration, 0, 0, 0)))
    result = check_hold_at({"waypoint": "W1", "min_s": 5}, goal, readings, config)
    assert result.verdict == expected
    assert result.observed_s == pytest.approx(duration)


def test_return_mode_time_does_not_count_as_holding(mission_states, flight, config):
    _, _, goal = mission_states
    # Stay at W1 for six seconds, but enter RTL after two seconds.
    readings = replace(
        flight,
        position=tuple(TimedVec3(i / 10, 50, 0, 20) for i in range(61)),
        nav_state=(TimedInt(0, 3), TimedInt(2, 5)),
    )
    result = check_hold_at({"waypoint": "W1", "min_s": 5}, goal, readings, config)
    assert result.verdict == "FAIL"
    assert result.observed_s == pytest.approx(2)


def test_log_ending_during_a_short_hold_is_inconclusive(mission_states, flight, config):
    _, _, goal = mission_states
    readings = replace(
        flight,
        position=(TimedVec3(0, 50, 0, 20), TimedVec3(0.1, 50, 0, 20)),
        landed=(TimedBool(0, False),),
    )
    result = check_hold_at({"waypoint": "W1", "min_s": 5}, goal, readings, config)
    assert result.verdict == "INCONCLUSIVE"


@pytest.mark.parametrize("height, expected", [(35, "PASS"), (35.01, "FAIL")])
def test_geofence_height_boundary(mission_states, flight, config, height, expected):
    _, _, goal = mission_states
    readings = replace(flight, position=(TimedVec3(0, 0, 0, height),))
    result = check_stays_in_geofence(
        {"max_distance_m": 60, "max_height_m": 35}, goal, readings, config
    )
    assert result.verdict == expected


def test_missing_positions_cannot_prove_geofence_compliance(
    mission_states, flight, config
):
    _, _, goal = mission_states
    result = check_stays_in_geofence(
        {"max_distance_m": 60, "max_height_m": 35},
        goal,
        replace(flight, position=()),
        config,
    )
    assert result.verdict == "INCONCLUSIVE"


@pytest.mark.parametrize("reverse, expected", [(False, "PASS"), (True, "FAIL")])
def test_waypoint_order_requires_a_later_visit(
    mission_states, flight, config, reverse, expected
):
    _, _, goal = mission_states
    second = replace(goal.waypoints["W1"], id="W2", x=100)
    goal = replace(goal, waypoints={**goal.waypoints, "W2": second})
    xs = [100, 50] if reverse else [50, 100]
    readings = replace(
        flight, position=tuple(TimedVec3(i / 10, x, 0, 20) for i, x in enumerate(xs))
    )
    result = check_visits_in_order({"waypoints": ["W1", "W2"]}, goal, readings, config)
    assert result.verdict == expected


def test_engine_reports_later_checks_after_a_failure(mission_states, flight, config):
    mission, start, goal = mission_states
    result = verify(mission, start, goal, flight, config)
    assert result.verdict == "FAIL"  # The hold is much shorter than five seconds.
    assert [(c.check, c.verdict) for c in result.checks] == [
        ("visited", "PASS"),
        ("goal_check", "PASS"),
        ("hold_at", "FAIL"),
        ("disarmed_after_landing", "PASS"),
    ]


def test_engine_passes_a_complete_mission_with_matching_evidence(
    mission_states, flight, config
):
    mission, start, goal = mission_states
    # Hold at W1 from 0 to 5 s, return to base, touch down, then disarm.
    readings = replace(
        flight,
        position=tuple(TimedVec3(i / 10, 50, 0, 20) for i in range(50))
        + (TimedVec3(5, 0, 0, 0),),
        velocity=(TimedVec3(5.2, 0, 0, 0),),
        landed=(TimedBool(0, False), TimedBool(5.1, True)),
        arming_state=(TimedInt(0, 2), TimedInt(5.2, 1)),
        disarm_reason=(TimedInt(5.2, 6),),
        cross_check=CrossCheckData(
            verdict="PASS", compared=51, max_difference_m=0, publishers=1
        ),
    )
    result = verify(mission, start, goal, readings, config)
    assert result.verdict == "PASS"
    assert len(result.checks) == 5
    assert all(c.verdict == "PASS" for c in result.checks)


@pytest.mark.parametrize(
    "trigger_times, expected", [((0,), "PASS"), ((0.1,), "FAIL"), ((), "FAIL")]
)
def test_camera_trigger_must_happen_at_the_waypoint(
    mission_states, flight, config, trigger_times, expected
):
    _, start, goal = mission_states
    # At 0 s the drone is at W1; at 0.1 s it is back at base.
    # This checks trigger evidence only; proving an actual photo is still open.
    waypoint = replace(goal.waypoints["W1"], clicked_pic=True)
    readings = replace(flight, camera_triggered_at=trigger_times, camera_trigger_mode=1)
    result = check_clicked_pic(waypoint, start.waypoints["W1"], readings, config)
    assert result.verdict == expected


def test_camera_trigger_without_a_fresh_position_is_inconclusive(
    mission_states, flight, config
):
    _, start, goal = mission_states
    waypoint = replace(goal.waypoints["W1"], clicked_pic=True)
    readings = replace(flight, camera_triggered_at=(1,), camera_trigger_mode=1)
    result = check_clicked_pic(waypoint, start.waypoints["W1"], readings, config)
    assert result.verdict == "INCONCLUSIVE"


def test_bad_independent_evidence_makes_overall_verdict_inconclusive(
    mission_states, flight, config
):
    mission, start, goal = mission_states
    readings = replace(
        flight, cross_check=CrossCheckData(verdict="FAIL", compared=2, over_limit=1)
    )
    result = verify(mission, start, goal, readings, config)
    assert result.verdict == "INCONCLUSIVE"
    assert next(c for c in result.checks if c.check == "hold_at").verdict == "FAIL"
    assert result.checks[-1].verdict == "INCONCLUSIVE"


def test_harness_timeout_marks_every_check_inconclusive(mission_states, flight, config):
    mission, start, goal = mission_states
    readings = replace(flight, run_status="inconclusive", reason="timeout")
    result = verify(mission, start, goal, readings, config)
    assert result.verdict == "INCONCLUSIVE"
    assert len(result.checks) == 4
    assert all(
        c.verdict == "INCONCLUSIVE" and "timeout" in c.reason for c in result.checks
    )


def test_readings_from_another_mission_are_rejected(mission_states, flight, config):
    mission, start, goal = mission_states
    with pytest.raises(VerifierInputError, match="mission_id mismatch"):
        verify(mission, start, goal, replace(flight, mission_id="OTHER"), config)


def test_out_of_order_timestamps_are_rejected(mission_states, flight, config):
    mission, start, goal = mission_states
    readings = replace(flight, position=tuple(reversed(flight.position)))
    with pytest.raises(VerifierInputError, match="not sorted"):
        verify(mission, start, goal, readings, config)
