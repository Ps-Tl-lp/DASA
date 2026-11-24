from __future__ import annotations

import math

from ..config import VerifierConfig
from ..models import CheckResult, EnvState, Readings
from ..timeseries import EPS, ended_on_ground, missing_topics_for


def _resolve_not_in_log(
    start_state: EnvState,
    config: VerifierConfig,
) -> dict[str, object]:
    resolved: dict[str, object] = {}
    vehicle_type = start_state.agent.vehicle_type

    for prop, source in config.not_in_log.items():
        if source == "start_state":
            attr = prop.removeprefix("agent.")
            resolved[prop] = getattr(start_state.agent, attr, None)
        elif source == "vehicle_type":
            if vehicle_type is not None and vehicle_type in config.vehicle_types:
                vt_spec = config.vehicle_types[vehicle_type]
                attr = prop.removeprefix("agent.")
                resolved[prop] = getattr(vt_spec, attr, None)
            else:
                resolved[prop] = None
    return resolved


def check_goal(
    start_state: EnvState,
    goal_state: EnvState,
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    goal_agent = goal_state.agent
    needs_pos = (
        goal_agent.x is not None or goal_agent.y is not None or goal_agent.z is not None
    )
    needs_vel = (
        goal_agent.vx is not None
        or goal_agent.vy is not None
        or goal_agent.vz is not None
    )
    needs_landed = goal_agent.landed is not None

    needed_readings: list[str] = []
    if needs_pos:
        needed_readings.extend(["agent.x", "agent.y", "agent.z"])
    if needs_vel:
        needed_readings.extend(
            ["agent.velocity.x", "agent.velocity.y", "agent.velocity.z"]
        )
    if needs_landed:
        needed_readings.append("agent.landed")

    missing_topics = missing_topics_for(readings, config, needed_readings)
    if missing_topics:
        return CheckResult(
            check="goal_check",
            verdict="INCONCLUSIVE",
            reason=(
                f"Missing required log topic(s) for goal_check: "
                f"{', '.join(missing_topics)}"
            ),
        )

    missing: list[str] = []
    if needs_pos and not readings.position:
        missing.append("position")
    if needs_vel and not readings.velocity:
        missing.append("velocity")
    if needs_landed and not readings.landed:
        missing.append("landed")
    if missing:
        return CheckResult(
            check="goal_check",
            verdict="INCONCLUSIVE",
            reason=f"Missing required readings for goal_check: {', '.join(missing)}",
        )

    failures: list[str] = []
    dist_m: float | None = None
    speed_m_s: float | None = None
    last_landed: bool | None = readings.landed[-1].value if readings.landed else None

    if needs_pos:
        last_pos = readings.position[-1]
        dx = (last_pos.x - goal_agent.x) if goal_agent.x is not None else 0.0
        dy = (last_pos.y - goal_agent.y) if goal_agent.y is not None else 0.0
        dz = (last_pos.z - goal_agent.z) if goal_agent.z is not None else 0.0
        dist_m = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist_m > config.goal_check.max_distance_m + EPS:
            failures.append(
                f"{dist_m:.2f} m from goal position "
                f"(limit {config.goal_check.max_distance_m} m)"
            )

    if needs_vel:
        last_vel = readings.velocity[-1]
        dvx = (last_vel.x - goal_agent.vx) if goal_agent.vx is not None else 0.0
        dvy = (last_vel.y - goal_agent.vy) if goal_agent.vy is not None else 0.0
        dvz = (last_vel.z - goal_agent.vz) if goal_agent.vz is not None else 0.0
        speed_m_s = math.sqrt(dvx * dvx + dvy * dvy + dvz * dvz)
        if speed_m_s > config.goal_check.max_speed_m_s + EPS:
            failures.append(
                f"speed {speed_m_s:.2f} m/s "
                f"(limit {config.goal_check.max_speed_m_s} m/s)"
            )

    if needs_landed and last_landed != goal_agent.landed:
        failures.append(f"landed is {last_landed} (expected {goal_agent.landed})")

    # Exact comparison for not_in_log properties listed in goal.xml
    not_in_log = _resolve_not_in_log(start_state, config)
    for prop, attr in (
        ("agent.vehicle_type", "vehicle_type"),
        ("agent.has_camera", "has_camera"),
        ("agent.has_grippers", "has_grippers"),
    ):
        expected = getattr(goal_agent, attr)
        if expected is not None:
            actual = not_in_log.get(prop)
            if actual != expected:
                failures.append(f"{prop} is {actual!r} (expected {expected!r})")

    if not failures:
        parts: list[str] = []
        if dist_m is not None:
            parts.append(f"Ends {dist_m:.2f} m from the goal's position")
        if last_landed is True:
            parts.append("landed")
        elif last_landed is False:
            parts.append("airborne")
        if speed_m_s is not None:
            parts.append(f"at {speed_m_s:.2f} m/s")
        reason = ", ".join(parts) if parts else "All goal properties matched"
        return CheckResult(check="goal_check", verdict="PASS", reason=reason)

    if not ended_on_ground(readings):
        detail = (
            f" ({dist_m:.2f} m from the goal's position)" if dist_m is not None else ""
        )
        return CheckResult(
            check="goal_check",
            verdict="INCONCLUSIVE",
            reason=f"Log ended before landing{detail}",
        )

    return CheckResult(
        check="goal_check",
        verdict="FAIL",
        reason=f"Goal state not met at end of flight: {'; '.join(failures)}",
    )
