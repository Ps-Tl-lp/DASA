from __future__ import annotations

from dataclasses import dataclass

from ..config import VerifierConfig
from ..models import CheckResult, Readings
from ..timeseries import TimeSeries, missing_topics_for


@dataclass(frozen=True)
class _DisarmEvent:
    t_s: float
    reason: int | None


def check_disarmed_after_landing(
    readings: Readings,
    config: VerifierConfig,
) -> CheckResult:
    missing_topics = missing_topics_for(
        readings, config, ("arming_state", "disarm_reason", "agent.landed")
    )
    if missing_topics:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="INCONCLUSIVE",
            reason=(
                "Missing required log topic(s) to verify disarm after landing: "
                f"{', '.join(missing_topics)}"
            ),
        )

    if not readings.landed or not readings.arming_state:
        missing = []
        if not readings.landed:
            missing.append("landed")
        if not readings.arming_state:
            missing.append("arming_state")
        return CheckResult(
            check="disarmed_after_landing",
            verdict="INCONCLUSIVE",
            reason=(
                f"Missing {', '.join(missing)} readings to verify disarm after landing"
            ),
        )

    disarm_cfg = config.disarmed_after_landing
    disarmed_val = disarm_cfg.disarmed_state
    expected_reason = disarm_cfg.expected_reason
    reason_ts = TimeSeries(readings.disarm_reason)

    # Disarm = arming_state transitioning from non-disarmed to disarmed_state
    disarms: list[_DisarmEvent] = []
    for prev, curr in zip(
        readings.arming_state, readings.arming_state[1:], strict=False
    ):
        if prev.value != disarmed_val and curr.value == disarmed_val:
            r_sample = reason_ts.at_or_before(curr.t_s)
            disarms.append(
                _DisarmEvent(
                    t_s=curr.t_s,
                    reason=r_sample.value if r_sample is not None else None,
                )
            )

    airborne_indices = [
        i for i, sample in enumerate(readings.landed) if not sample.value
    ]
    if not airborne_indices:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="INCONCLUSIVE",
            reason="Log shows no takeoff (no airborne landed=false reading)",
        )

    takeoff_t = readings.landed[airborne_indices[0]].t_s
    last_airborne_idx = airborne_indices[-1]
    touchdown_t: float | None = (
        readings.landed[last_airborne_idx + 1].t_s
        if last_airborne_idx + 1 < len(readings.landed)
        else None
    )

    # Check for any disarm in the air (between takeoff and touchdown,
    # or after takeoff if never landed)
    mid_air_disarms = [
        d
        for d in disarms
        if d.t_s >= takeoff_t and (touchdown_t is None or d.t_s < touchdown_t)
    ]
    if mid_air_disarms:
        first = mid_air_disarms[0]
        return CheckResult(
            check="disarmed_after_landing",
            verdict="FAIL",
            reason=(
                f"Disarmed in the air at {first.t_s:.3f} s "
                f"(reason {first.reason}, takeoff at {takeoff_t:.3f} s)"
            ),
        )

    if touchdown_t is None:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="INCONCLUSIVE",
            reason="Log ended in mid-air with no touchdown recorded",
        )

    post_touchdown_disarms = [d for d in disarms if d.t_s >= touchdown_t]
    if not post_touchdown_disarms:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="INCONCLUSIVE",
            reason=f"No disarm recorded after touchdown at {touchdown_t:.3f} s",
        )

    last_disarm = post_touchdown_disarms[-1]
    if last_disarm.reason is None:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="INCONCLUSIVE",
            reason=(
                f"Disarmed at {last_disarm.t_s:.3f} s after touchdown, "
                "but disarm_reason is missing"
            ),
        )

    if last_disarm.reason != expected_reason:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="FAIL",
            reason=(
                f"Last disarm after touchdown at {last_disarm.t_s:.3f} s had reason "
                f"{last_disarm.reason} (expected {expected_reason})"
            ),
        )

    if readings.arming_state[-1].value != disarmed_val:
        return CheckResult(
            check="disarmed_after_landing",
            verdict="FAIL",
            reason=(
                f"Disarmed at {last_disarm.t_s:.3f} s after touchdown, "
                f"but log ended with arming_state {readings.arming_state[-1].value}"
            ),
        )

    delay_s = last_disarm.t_s - touchdown_t
    return CheckResult(
        check="disarmed_after_landing",
        verdict="PASS",
        reason=(
            f"Disarmed with reason {last_disarm.reason} at {last_disarm.t_s:.3f} s, "
            f"{delay_s:.3f} s after touchdown at {touchdown_t:.3f} s, "
            "and still disarmed at the end"
        ),
    )
