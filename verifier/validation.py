from __future__ import annotations

from collections.abc import Sequence

from .models import EnvState, Mission, Readings
from .timeseries import Timed


class VerifierInputError(ValueError):
    """Raised when input files violate structural or contract invariants."""


def _assert_monotonic(name: str, samples: Sequence[Timed]) -> None:
    for prev, curr in zip(samples, samples[1:], strict=False):
        if curr.t_s < prev.t_s:
            raise VerifierInputError(
                f"Readings series '{name}' is not sorted by t_s: "
                f"{curr.t_s} follows {prev.t_s}"
            )


def _assert_monotonic_floats(name: str, values: Sequence[float]) -> None:
    for prev, curr in zip(values, values[1:], strict=False):
        if curr < prev:
            raise VerifierInputError(
                f"Readings series '{name}' is not sorted by t_s: {curr} follows {prev}"
            )


def validate_inputs(
    mission: Mission,
    goal_state: EnvState,
    readings: Readings,
) -> None:
    if readings.mission_id != mission.mission_id:
        raise VerifierInputError(
            f"mission_id mismatch: mission has '{mission.mission_id}', "
            f"readings has '{readings.mission_id}'"
        )

    if readings.run_status not in {"completed", "inconclusive"}:
        raise VerifierInputError(
            f"Invalid run_status '{readings.run_status}' "
            f"(expected 'completed' or 'inconclusive')"
        )

    _assert_monotonic("position", readings.position)
    _assert_monotonic("velocity", readings.velocity)
    _assert_monotonic("landed", readings.landed)
    _assert_monotonic("nav_state", readings.nav_state)
    _assert_monotonic("arming_state", readings.arming_state)
    _assert_monotonic("disarm_reason", readings.disarm_reason)
    _assert_monotonic_floats("camera_triggered_at", readings.camera_triggered_at)

    for spec in mission.postconditions:
        if spec.name == "hold_at":
            wp_id = str(spec.params.get("waypoint", ""))
            if wp_id not in goal_state.waypoints:
                raise VerifierInputError(
                    f"Postcondition hold_at references unknown waypoint '{wp_id}'"
                )
        elif spec.name == "visits_in_order":
            for wp_id in spec.params.get("waypoints", []):
                if str(wp_id) not in goal_state.waypoints:
                    raise VerifierInputError(
                        "Postcondition visits_in_order references unknown waypoint "
                        f"'{wp_id}'"
                    )
