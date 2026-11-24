from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Outcome = Literal["PASS", "FAIL", "INCONCLUSIVE"]


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class TimedVec3:
    t_s: float
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class TimedBool:
    t_s: float
    value: bool


@dataclass(frozen=True)
class TimedInt:
    t_s: float
    value: int


@dataclass(frozen=True)
class CrossCheckData:
    verdict: str
    recording: str | None = None
    compared: int = 0
    unmatched: int = 0
    over_limit: int = 0
    max_difference_m: float | None = None
    publishers: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Readings:
    mission_id: str
    run_id: str
    run_status: str
    reason: str | None
    position: tuple[TimedVec3, ...]
    velocity: tuple[TimedVec3, ...]
    landed: tuple[TimedBool, ...]
    nav_state: tuple[TimedInt, ...]
    arming_state: tuple[TimedInt, ...]
    disarm_reason: tuple[TimedInt, ...]
    camera_triggered_at: tuple[float, ...] = ()
    camera_trigger_mode: int | None = None
    time_zero_us: int | None = None
    sources: str | dict[str, str] | None = None
    missing_topics: tuple[str, ...] = ()
    cross_check: CrossCheckData | None = None


@dataclass(frozen=True)
class BaseState:
    id: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class AgentState:
    id: str
    base_id: str | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None
    landed: bool | None = None
    vehicle_type: str | None = None
    has_camera: bool | None = None
    has_grippers: bool | None = None


@dataclass(frozen=True)
class WaypointState:
    id: str
    x: float
    y: float
    z: float
    visited: bool | None = None
    clicked_pic: bool | None = None  # None means omitted in XML


@dataclass(frozen=True)
class EnvState:
    id: str
    env_type: str
    base: BaseState
    agent: AgentState
    waypoints: dict[str, WaypointState]  # preserves XML declaration order


@dataclass(frozen=True)
class PostconditionSpec:
    name: str
    params: dict[str, Any]


@dataclass(frozen=True)
class Mission:
    mission_id: str
    start_path: str
    goal_path: str
    postconditions: tuple[PostconditionSpec, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    check: str
    verdict: Outcome
    reason: str
    waypoint: str | None = None
    expected_s: float | int | None = None
    observed_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.check}
        if self.waypoint is not None:
            out["waypoint"] = self.waypoint
        out["verdict"] = self.verdict
        if self.expected_s is not None:
            out["expected_s"] = self.expected_s
        if self.observed_s is not None:
            out["observed_s"] = round(self.observed_s, 2)
        out["reason"] = self.reason
        return out


@dataclass(frozen=True)
class Verdict:
    mission_id: str
    run_id: str
    verdict: Outcome
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "run_id": self.run_id,
            "verdict": self.verdict,
            "checks": [c.to_dict() for c in self.checks],
        }
