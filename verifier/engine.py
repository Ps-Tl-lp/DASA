from __future__ import annotations

from .checks import (
    check_clicked_pic,
    check_disarmed_after_landing,
    check_evidence_cross_check,
    check_goal,
    check_postcondition,
    check_visited,
)
from .config import VerifierConfig
from .models import CheckResult, EnvState, Mission, Outcome, Readings, Verdict
from .validation import validate_inputs


def aggregate_verdict(
    checks: list[CheckResult],
    cross_check_failed: bool,
) -> Outcome:
    if cross_check_failed:
        return "INCONCLUSIVE"
    if any(c.verdict == "FAIL" for c in checks):
        return "FAIL"
    if any(c.verdict == "INCONCLUSIVE" for c in checks):
        return "INCONCLUSIVE"
    return "PASS"


def _inconclusive_checks_for_harness(
    mission: Mission,
    goal_state: EnvState,
    readings: Readings,
) -> tuple[CheckResult, ...]:
    reason = (
        f"Harness marked run inconclusive ({readings.reason})"
        if readings.reason
        else "Harness marked run inconclusive"
    )
    checks: list[CheckResult] = []

    for wp in goal_state.waypoints.values():
        if wp.visited is not None:
            checks.append(
                CheckResult("visited", "INCONCLUSIVE", reason, waypoint=wp.id)
            )
        if wp.clicked_pic is not None:
            checks.append(
                CheckResult("clicked_pic", "INCONCLUSIVE", reason, waypoint=wp.id)
            )

    checks.append(CheckResult("goal_check", "INCONCLUSIVE", reason))

    for spec in mission.postconditions:
        if spec.name == "hold_at":
            checks.append(
                CheckResult(
                    check="hold_at",
                    waypoint=str(spec.params["waypoint"]),
                    verdict="INCONCLUSIVE",
                    expected_s=spec.params["min_s"],
                    reason=reason,
                )
            )
        else:
            checks.append(CheckResult(spec.name, "INCONCLUSIVE", reason))

    checks.append(CheckResult("disarmed_after_landing", "INCONCLUSIVE", reason))

    if readings.cross_check is not None:
        checks.append(CheckResult("evidence_cross_check", "INCONCLUSIVE", reason))

    return tuple(checks)


def verify(
    mission: Mission,
    start_state: EnvState,
    goal_state: EnvState,
    readings: Readings,
    config: VerifierConfig,
) -> Verdict:
    """Run every applicable check in canonical order with no early exit."""
    validate_inputs(mission, goal_state, readings)
    if readings.run_status == "inconclusive":
        return Verdict(
            mission_id=readings.mission_id,
            run_id=readings.run_id,
            verdict="INCONCLUSIVE",
            checks=_inconclusive_checks_for_harness(mission, goal_state, readings),
        )

    checks: list[CheckResult] = []

    # 1. Derived waypoint checks
    for wp in goal_state.waypoints.values():
        start_wp = start_state.waypoints.get(wp.id)
        if wp.visited is not None:
            checks.append(check_visited(wp, start_wp, readings, config))
        if wp.clicked_pic is not None:
            checks.append(check_clicked_pic(wp, start_wp, readings, config))

    # 2. Goal state check
    checks.append(check_goal(start_state, goal_state, readings, config))

    # 3. Mission postconditions in listed order
    for spec in mission.postconditions:
        checks.append(check_postcondition(spec, goal_state, readings, config))

    # 4. Implicit check: runs on every mission
    checks.append(check_disarmed_after_landing(readings, config))

    # 5. Evidence cross-check: recorded runs only
    cross_check_failed = False
    if readings.cross_check is not None:
        cc_result = check_evidence_cross_check(readings, config)
        checks.append(cc_result)
        cross_check_failed = cc_result.verdict != "PASS"

    overall = aggregate_verdict(checks, cross_check_failed)
    return Verdict(
        mission_id=readings.mission_id,
        run_id=readings.run_id,
        verdict=overall,
        checks=tuple(checks),
    )
