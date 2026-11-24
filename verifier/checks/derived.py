from __future__ import annotations

from hydra_geometry import at_waypoint

from ..config import VerifierConfig
from ..models import CheckResult, Readings, WaypointState
from ..timeseries import (
    EPS,
    TimeSeries,
    ended_on_ground,
    find_position_gaps,
    missing_topics_for,
)


def check_visited(
    waypoint: WaypointState,
    start_waypoint: WaypointState | None,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    if start_waypoint is not None and start_waypoint.visited is True:
        if waypoint.visited is True:
            return CheckResult(
                check="visited",
                waypoint=waypoint.id,
                verdict="PASS",
                reason=(
                    f"{waypoint.id} was already visited in the start state; "
                    "the goal keeps visited true"
                ),
            )
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="FAIL",
            reason=(
                f"{waypoint.id} was already visited in the start state, "
                "but the goal has visited false"
            ),
        )

    missing = missing_topics_for(readings, config, ("agent.x", "agent.y", "agent.z"))
    if missing:
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"Missing required log topic(s) to verify visit: {', '.join(missing)}"
            ),
        )

    if not readings.position:
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"No position readings available to check whether "
                f"{waypoint.id} was visited"
            ),
        )

    zone = config.at_waypoint
    first_hit_t: float | None = None
    for pos in readings.position:
        if at_waypoint(
            pos,
            waypoint,
            within_m=zone.within_m,
            height_within_m=zone.height_within_m,
            edge_counts_as_inside=zone.edge_counts_as_inside,
        ):
            first_hit_t = pos.t_s
            break

    goal_wants_visit = bool(waypoint.visited)
    gaps = find_position_gaps(readings.position, config.log_gap_max_s)
    on_ground = ended_on_ground(readings)

    if goal_wants_visit:
        if first_hit_t is not None:
            return CheckResult(
                check="visited",
                waypoint=waypoint.id,
                verdict="PASS",
                reason=(
                    f"First at {waypoint.id} at {first_hit_t:.3f} s; "
                    "the goal has visited true"
                ),
            )
        if not on_ground:
            return CheckResult(
                check="visited",
                waypoint=waypoint.id,
                verdict="INCONCLUSIVE",
                reason=f"Never reached {waypoint.id}, and the log ended before landing",
            )
        if gaps:
            t0, t1 = gaps[0]
            return CheckResult(
                check="visited",
                waypoint=waypoint.id,
                verdict="INCONCLUSIVE",
                reason=(
                    f"No visit to {waypoint.id} recorded, but a log gap from "
                    f"{t0:.3f} s to {t1:.3f} s could hide a visit"
                ),
            )
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="FAIL",
            reason=(
                f"Never entered {waypoint.id} before landing; the goal has visited true"
            ),
        )

    # Goal explicitly requires visited == false
    if first_hit_t is not None:
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="FAIL",
            reason=(
                f"Entered {waypoint.id} at {first_hit_t:.3f} s; "
                "the goal has visited false"
            ),
        )
    if not on_ground:
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"Did not visit {waypoint.id} so far, but the log ended before landing"
            ),
        )
    if gaps:
        t0, t1 = gaps[0]
        return CheckResult(
            check="visited",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"No visit to {waypoint.id} recorded, but a log gap from "
                f"{t0:.3f} s to {t1:.3f} s could hide an entry"
            ),
        )
    return CheckResult(
        check="visited",
        waypoint=waypoint.id,
        verdict="PASS",
        reason=f"Never entered {waypoint.id}; the goal has visited false",
    )


def check_clicked_pic(
    waypoint: WaypointState,
    start_waypoint: WaypointState | None,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    if start_waypoint is not None and start_waypoint.clicked_pic is True:
        if waypoint.clicked_pic is True:
            return CheckResult(
                check="clicked_pic",
                waypoint=waypoint.id,
                verdict="PASS",
                reason=(
                    f"Picture at {waypoint.id} was already taken in the start state; "
                    "the goal keeps clicked_pic true"
                ),
            )
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="FAIL",
            reason=(
                f"Picture at {waypoint.id} was already taken in the start state, "
                "but the goal has clicked_pic false"
            ),
        )

    missing = missing_topics_for(
        readings, config, ("agent.x", "agent.y", "agent.z", "camera_triggered_at")
    )
    if missing:
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                "Missing required log topic(s) to verify camera trigger: "
                f"{', '.join(missing)}"
            ),
        )

    zone = config.at_waypoint
    goal_wants_pic = bool(waypoint.clicked_pic)

    if not readings.position:
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"No position readings available to verify camera trigger at "
                f"{waypoint.id}"
            ),
        )

    pos_ts = TimeSeries(readings.position)
    first_valid_hit_t: float | None = None
    ambiguous_trigger_t: float | None = None

    for trig_t in readings.camera_triggered_at:
        pos = pos_ts.at_or_before(trig_t)
        if pos is None or (trig_t - pos.t_s) > (config.log_gap_max_s + EPS):
            # Trigger occurred before position telemetry or across a position gap
            if ambiguous_trigger_t is None:
                ambiguous_trigger_t = trig_t
            continue

        if at_waypoint(
            pos,
            waypoint,
            within_m=zone.within_m,
            height_within_m=zone.height_within_m,
            edge_counts_as_inside=zone.edge_counts_as_inside,
        ):
            first_valid_hit_t = trig_t
            break

    on_ground = ended_on_ground(readings)

    if goal_wants_pic:
        if first_valid_hit_t is not None:
            return CheckResult(
                check="clicked_pic",
                waypoint=waypoint.id,
                verdict="PASS",
                reason=(
                    f"Camera triggered at {waypoint.id} at {first_valid_hit_t:.3f} s; "
                    f"the goal has clicked_pic true"
                ),
            )

        if readings.camera_trigger_mode != 1:
            return CheckResult(
                check="clicked_pic",
                waypoint=waypoint.id,
                verdict="INCONCLUSIVE",
                reason=(
                    f"Goal requires a picture at {waypoint.id}, but "
                    f"camera_trigger_mode is {readings.camera_trigger_mode} "
                    "(expected 1)"
                ),
            )

        if ambiguous_trigger_t is not None:
            return CheckResult(
                check="clicked_pic",
                waypoint=waypoint.id,
                verdict="INCONCLUSIVE",
                reason=(
                    f"Camera triggered at {ambiguous_trigger_t:.3f} s without a fresh "
                    f"position sample (within {config.log_gap_max_s} s) to confirm "
                    f"location at {waypoint.id}"
                ),
            )

        if not on_ground:
            return CheckResult(
                check="clicked_pic",
                waypoint=waypoint.id,
                verdict="INCONCLUSIVE",
                reason=(
                    f"No camera trigger at {waypoint.id} before the log ended in "
                    f"mid-air"
                ),
            )

        # Note: camera_capture in missing_topics is expected when TRIG_MODE=1 and
        # 0 triggers fired
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="FAIL",
            reason=(
                f"Camera never triggered while at {waypoint.id} "
                f"(camera_trigger_mode={readings.camera_trigger_mode})"
            ),
        )

    # Goal explicitly requires clicked_pic == false
    if first_valid_hit_t is not None:
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="FAIL",
            reason=(
                f"Camera triggered at {waypoint.id} at {first_valid_hit_t:.3f} s; "
                f"the goal has clicked_pic false"
            ),
        )

    if ambiguous_trigger_t is not None:
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"Camera triggered at {ambiguous_trigger_t:.3f} s without a fresh "
                f"position sample to rule out a trigger at {waypoint.id}"
            ),
        )

    if not on_ground:
        return CheckResult(
            check="clicked_pic",
            waypoint=waypoint.id,
            verdict="INCONCLUSIVE",
            reason=(
                f"No camera trigger at {waypoint.id} so far, but the log ended in "
                f"mid-air"
            ),
        )

    return CheckResult(
        check="clicked_pic",
        waypoint=waypoint.id,
        verdict="PASS",
        reason=(
            f"Camera never triggered at {waypoint.id}; the goal has clicked_pic false"
        ),
    )
