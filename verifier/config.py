from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class WaypointZoneConfig:
    within_m: float
    height_within_m: float
    edge_counts_as_inside: bool


@dataclass(frozen=True)
class GoalCheckConfig:
    max_distance_m: float
    max_speed_m_s: float


@dataclass(frozen=True)
class HoldAtConfig:
    in_nav_state: int
    short_by_at_most_s: float
    max_gap_s: float


@dataclass(frozen=True)
class DisarmConfig:
    disarmed_state: int
    expected_reason: int


@dataclass(frozen=True)
class CrossCheckConfig:
    max_difference_m: float
    same_time_within_s: float


@dataclass(frozen=True)
class VehicleTypeSpec:
    sim_model: str
    has_camera: bool
    has_grippers: bool


@dataclass(frozen=True)
class VerifierConfig:
    platform: str
    at_waypoint: WaypointZoneConfig
    goal_check: GoalCheckConfig
    hold_at: HoldAtConfig
    disarmed_after_landing: DisarmConfig
    cross_check: CrossCheckConfig
    log_gap_max_s: float
    vehicle_types: dict[str, VehicleTypeSpec]
    not_in_log: dict[str, str]
    recorded_reading_topics: dict[str, str] = field(default_factory=dict)
    log_only_reading_topics: dict[str, str] = field(default_factory=dict)


def resolve_ref(raw: dict[str, Any], value: Any, _seen: set[str] | None = None) -> Any:
    """Resolve dotted references against raw config.

    Example: 'tolerances.hold_short_by_s'.
    """
    if not isinstance(value, str) or "." not in value:
        return value

    parts = value.split(".")
    if parts[0] not in raw:
        return value

    seen = _seen or set()
    if value in seen:
        raise ValueError(f"Circular config reference detected: {value}")

    cur: Any = raw
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(
                f"Unresolvable config reference '{value}' (missing '{part}')"
            )
        cur = cur[part]

    return resolve_ref(raw, cur, seen | {value})


def load_config(path: Path) -> VerifierConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    tol = raw["tolerances"]
    wp_tol = tol["at_waypoint"]
    at_waypoint = WaypointZoneConfig(
        within_m=float(resolve_ref(raw, wp_tol["within_m"])),
        height_within_m=float(resolve_ref(raw, wp_tol["height_within_m"])),
        edge_counts_as_inside=bool(resolve_ref(raw, wp_tol["edge_counts_as_inside"])),
    )

    within_entries = raw["goal_check"]["within"]
    max_distance_m: float | None = None
    max_speed_m_s: float | None = None
    for entry in within_entries:
        if "max_distance" in entry:
            max_distance_m = float(resolve_ref(raw, entry["max_distance"]))
        if "max_speed" in entry:
            max_speed_m_s = float(resolve_ref(raw, entry["max_speed"]))
    if max_distance_m is None or max_speed_m_s is None:
        raise ValueError(
            "goal_check.within must define both max_distance and max_speed"
        )

    hold_raw = raw["postconditions"]["hold_at"]
    hold_at = HoldAtConfig(
        in_nav_state=int(resolve_ref(raw, hold_raw["in_nav_state"])),
        short_by_at_most_s=float(resolve_ref(raw, hold_raw["short_by_at_most"])),
        max_gap_s=float(resolve_ref(raw, hold_raw["max_gap"])),
    )

    disarm_raw = raw["postconditions"]["disarmed_after_landing"]
    disarmed = DisarmConfig(
        disarmed_state=int(resolve_ref(raw, disarm_raw["disarmed_state"])),
        expected_reason=int(resolve_ref(raw, disarm_raw["last_value"])),
    )

    cc_raw = raw["cross_check"]
    cross_check = CrossCheckConfig(
        max_difference_m=float(resolve_ref(raw, cc_raw["max_difference_m"])),
        same_time_within_s=float(resolve_ref(raw, cc_raw["same_time_within_s"])),
    )

    vehicle_types = {
        name: VehicleTypeSpec(
            sim_model=str(spec["sim_model"]),
            has_camera=bool(spec["has_camera"]),
            has_grippers=bool(spec["has_grippers"]),
        )
        for name, spec in raw["vehicle_types"].items()
    }

    recorded_reading_topics = {
        name: str(spec["topic"])
        for name, spec in raw.get("readings", {}).items()
        if spec.get("source") == "log" and "topic" in spec
    }
    log_only_reading_topics = {
        name: str(spec["topic"])
        for name, spec in raw.get("log_only_readings", {}).items()
        if spec.get("source") == "log" and "topic" in spec
    }

    return VerifierConfig(
        platform=str(raw["platform"]),
        at_waypoint=at_waypoint,
        goal_check=GoalCheckConfig(
            max_distance_m=max_distance_m,
            max_speed_m_s=max_speed_m_s,
        ),
        hold_at=hold_at,
        disarmed_after_landing=disarmed,
        cross_check=cross_check,
        log_gap_max_s=float(resolve_ref(raw, tol["log_gap_max_s"])),
        vehicle_types=vehicle_types,
        not_in_log=dict(raw.get("not_in_log", {})),
        recorded_reading_topics=recorded_reading_topics,
        log_only_reading_topics=log_only_reading_topics,
    )
