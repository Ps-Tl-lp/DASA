from __future__ import annotations

import math

from hydra_geometry import at_waypoint, inside_geofence

from ..config import VerifierConfig
from ..models import CheckResult, EnvState, PostconditionSpec, Readings
from ..timeseries import (
    EPS,
    TimeSeries,
    ended_on_ground,
    find_position_gaps,
    missing_topics_for,
)


def check_postcondition(
    spec: PostconditionSpec,
    goal_state: EnvState,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    if spec.name == "hold_at":
        return check_hold_at(spec.params, goal_state, readings, config)
    if spec.name == "visits_in_order":
        return check_visits_in_order(spec.params, goal_state, readings, config)
    if spec.name == "stays_in_geofence":
        return check_stays_in_geofence(spec.params, goal_state, readings, config)
    raise ValueError(f"Unsupported postcondition: {spec.name}")


def check_hold_at(
    params: dict,
    goal_state: EnvState,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    wp_id = str(params["waypoint"])
    expected_s = params["min_s"]  # preserve int/float formatting for verdict.json
    min_s = float(expected_s)

    if wp_id not in goal_state.waypoints:
        raise KeyError(f"hold_at references unknown waypoint '{wp_id}'")
    waypoint = goal_state.waypoints[wp_id]

    missing_topics = missing_topics_for(
        readings, config, ("agent.x", "agent.y", "agent.z", "nav_state")
    )
    if missing_topics:
        return CheckResult(
            check="hold_at",
            waypoint=wp_id,
            verdict="INCONCLUSIVE",
            expected_s=expected_s,
            observed_s=0.0,
            reason=(
                f"Missing required log topic(s) to evaluate hold at {wp_id}: "
                f"{', '.join(missing_topics)}"
            ),
        )

    if not readings.position or not readings.nav_state:
        missing = []
        if not readings.position:
            missing.append("position")
        if not readings.nav_state:
            missing.append("nav_state")
        return CheckResult(
            check="hold_at",
            waypoint=wp_id,
            verdict="INCONCLUSIVE",
            expected_s=expected_s,
            observed_s=0.0,
            reason=f"Missing {', '.join(missing)} readings to evaluate hold at {wp_id}",
        )

    zone = config.at_waypoint
    hold_cfg = config.hold_at
    nav_ts = TimeSeries(readings.nav_state)

    stretches: list[tuple[float, float]] = []
    active_start: float | None = None
    prev_p = None
    had_gap = False
    ended_in_zone = False

    for p in readings.position:
        if prev_p is not None and (p.t_s - prev_p.t_s) > (hold_cfg.max_gap_s + EPS):
            had_gap = True
            if active_start is not None:
                # Gap ends the stretch at the reading before the gap (no time credited)
                stretches.append((active_start, prev_p.t_s))
                active_start = None

        nav = nav_ts.at_or_before(p.t_s)
        in_mission_mode = nav is not None and nav.value == hold_cfg.in_nav_state
        in_zone = at_waypoint(
            p,
            waypoint,
            within_m=zone.within_m,
            height_within_m=zone.height_within_m,
            edge_counts_as_inside=zone.edge_counts_as_inside,
        )
        qualifies = in_mission_mode and in_zone

        if active_start is None:
            if qualifies:
                active_start = p.t_s
        elif not qualifies:
            # Normal exit: stretch ends at first reading outside zone/mission mode
            stretches.append((active_start, p.t_s))
            active_start = None

        prev_p = p

    if active_start is not None and prev_p is not None:
        ended_in_zone = True
        stretches.append((active_start, prev_p.t_s))

    threshold_s = min_s - hold_cfg.short_by_at_most_s
    if stretches:
        best_start, best_end = max(stretches, key=lambda s: s[1] - s[0])
        best_duration = best_end - best_start
    else:
        best_start, best_end, best_duration = None, None, 0.0

    visit_label = "Only visit" if len(stretches) == 1 else "Longest visit"

    if best_duration + EPS >= threshold_s:
        return CheckResult(
            check="hold_at",
            waypoint=wp_id,
            verdict="PASS",
            expected_s=expected_s,
            observed_s=best_duration,
            reason=(
                f"{visit_label} in mission mode ended at {best_end:.3f} s "
                f"after entering at {best_start:.3f} s"
            ),
        )

    if ended_in_zone:
        return CheckResult(
            check="hold_at",
            waypoint=wp_id,
            verdict="INCONCLUSIVE",
            expected_s=expected_s,
            observed_s=best_duration,
            reason=(
                f"Log ended while drone was still holding at {wp_id} "
                f"(observed {best_duration:.2f} s, needed {min_s:g} s)"
            ),
        )

    if had_gap:
        return CheckResult(
            check="hold_at",
            waypoint=wp_id,
            verdict="INCONCLUSIVE",
            expected_s=expected_s,
            observed_s=best_duration,
            reason=(
                f"Longest hold at {wp_id} was {best_duration:.2f} s "
                f"(needed {min_s:g} s), but a position gap exceeded "
                f"{hold_cfg.max_gap_s} s"
            ),
        )

    if not ended_on_ground(readings):
        return CheckResult(
            check="hold_at",
            waypoint=wp_id,
            verdict="INCONCLUSIVE",
            expected_s=expected_s,
            observed_s=best_duration,
            reason=(
                f"No qualifying hold at {wp_id} before log ended in mid-air "
                f"(longest {best_duration:.2f} s, needed {min_s:g} s)"
            ),
        )

    if best_start is None:
        reason = f"Never held at {wp_id} while in mission mode (needed {min_s:g} s)"
    else:
        reason = (
            f"{visit_label} in mission mode ended at {best_end:.3f} s "
            f"after entering at {best_start:.3f} s"
        )
    return CheckResult(
        check="hold_at",
        waypoint=wp_id,
        verdict="FAIL",
        expected_s=expected_s,
        observed_s=best_duration,
        reason=reason,
    )


def check_visits_in_order(
    params: dict,
    goal_state: EnvState,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    wp_ids = [str(w) for w in params.get("waypoints", [])]
    for wp_id in wp_ids:
        if wp_id not in goal_state.waypoints:
            raise KeyError(f"visits_in_order references unknown waypoint '{wp_id}'")

    if not wp_ids:
        return CheckResult(
            check="visits_in_order",
            verdict="PASS",
            reason="No waypoints listed for ordering check",
        )

    missing_topics = missing_topics_for(
        readings, config, ("agent.x", "agent.y", "agent.z")
    )
    if missing_topics:
        return CheckResult(
            check="visits_in_order",
            verdict="INCONCLUSIVE",
            reason=(
                f"Missing required log topic(s) to check visit order: "
                f"{', '.join(missing_topics)}"
            ),
        )

    if not readings.position:
        return CheckResult(
            check="visits_in_order",
            verdict="INCONCLUSIVE",
            reason=(
                f"No position readings available to check visit order "
                f"({', '.join(wp_ids)})"
            ),
        )

    zone = config.at_waypoint
    matched: list[tuple[str, float]] = []
    target_idx = 0
    last_match_t: float | None = None

    for pos in readings.position:
        if target_idx >= len(wp_ids):
            break
        if last_match_t is not None and pos.t_s <= last_match_t:
            continue

        target_wp = goal_state.waypoints[wp_ids[target_idx]]
        if at_waypoint(
            pos,
            target_wp,
            within_m=zone.within_m,
            height_within_m=zone.height_within_m,
            edge_counts_as_inside=zone.edge_counts_as_inside,
        ):
            matched.append((target_wp.id, pos.t_s))
            last_match_t = pos.t_s
            target_idx += 1

    if target_idx == len(wp_ids):
        summary = ", ".join(f"{wp_id} at {t:.3f} s" for wp_id, t in matched)
        return CheckResult(
            check="visits_in_order",
            verdict="PASS",
            reason=f"Visited waypoints in order: {summary}",
        )

    next_expected = wp_ids[target_idx]
    gaps = find_position_gaps(readings.position, config.log_gap_max_s)

    if not ended_on_ground(readings):
        return CheckResult(
            check="visits_in_order",
            verdict="INCONCLUSIVE",
            reason=(
                f"Matched {target_idx} of {len(wp_ids)} waypoints in order "
                f"(next expected {next_expected}), but the log ended in mid-air"
            ),
        )

    if gaps:
        t0, t1 = gaps[0]
        return CheckResult(
            check="visits_in_order",
            verdict="INCONCLUSIVE",
            reason=(
                f"Did not match {next_expected} in order, and a position gap from "
                f"{t0:.3f} s to {t1:.3f} s could hide a visit"
            ),
        )

    if matched:
        prev_wp, prev_t = matched[-1]
        detail = f"did not visit {next_expected} after {prev_wp} at {prev_t:.3f} s"
    else:
        detail = f"never reached first waypoint {next_expected}"

    return CheckResult(
        check="visits_in_order",
        verdict="FAIL",
        reason=f"Waypoints were not visited in order ({', '.join(wp_ids)}): {detail}",
    )


def check_stays_in_geofence(
    params: dict,
    goal_state: EnvState,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    max_distance_m = float(params["max_distance_m"])
    max_height_m = float(params["max_height_m"])
    base = goal_state.base

    missing_topics = missing_topics_for(
        readings, config, ("agent.x", "agent.y", "agent.z")
    )
    if missing_topics:
        return CheckResult(
            check="stays_in_geofence",
            verdict="INCONCLUSIVE",
            reason=(
                f"Missing required log topic(s) to check geofence: "
                f"{', '.join(missing_topics)}"
            ),
        )

    if not readings.position:
        return CheckResult(
            check="stays_in_geofence",
            verdict="INCONCLUSIVE",
            reason="No position readings available to check geofence",
        )

    for pos in readings.position:
        if not inside_geofence(
            pos,
            base,
            max_distance_m=max_distance_m,
            max_height_m=max_height_m,
            clearance_m=0.0,
            edge_counts_as_inside=True,
        ):
            horiz = math.hypot(pos.x - base.x, pos.y - base.y)
            height = pos.z - base.z
            return CheckResult(
                check="stays_in_geofence",
                verdict="FAIL",
                reason=(
                    f"Left geofence at {pos.t_s:.3f} s: {horiz:.2f} m horizontal "
                    f"(limit {max_distance_m:g} m), {height:.2f} m height "
                    f"(limit {max_height_m:g} m)"
                ),
            )

    if not ended_on_ground(readings):
        return CheckResult(
            check="stays_in_geofence",
            verdict="INCONCLUSIVE",
            reason=(
                f"Stayed inside geofence ({max_distance_m:g} m horizontal, "
                f"{max_height_m:g} m height) so far, but the log ended in mid-air"
            ),
        )

    gaps = find_position_gaps(readings.position, config.log_gap_max_s)
    if gaps:
        t0, t1 = gaps[0]
        return CheckResult(
            check="stays_in_geofence",
            verdict="INCONCLUSIVE",
            reason=(
                f"No geofence breach observed, but a position gap from "
                f"{t0:.3f} s to {t1:.3f} s could hide an excursion"
            ),
        )

    return CheckResult(
        check="stays_in_geofence",
        verdict="PASS",
        reason=(
            f"All {len(readings.position)} position samples stayed inside geofence "
            f"({max_distance_m:g} m horizontal, {max_height_m:g} m height)"
        ),
    )
