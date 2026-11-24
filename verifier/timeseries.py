from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from .models import Readings, TimedVec3

if TYPE_CHECKING:
    from .config import VerifierConfig

EPS = 1e-9


class Timed(Protocol):
    t_s: float


class TimeSeries[T: Timed]:
    """Indexed wrapper over a time-sorted sequence for O(log n) as-of lookups."""

    def __init__(self, samples: Sequence[T]) -> None:
        self._samples = samples
        self._times = [s.t_s for s in samples]

    def __len__(self) -> int:
        return len(self._samples)

    def at_or_before(self, t_s: float) -> T | None:
        idx = bisect_right(self._times, t_s) - 1
        if idx < 0:
            return None
        return self._samples[idx]


def ended_on_ground(readings: Readings) -> bool:
    """Return True only when landed telemetry exists and ends with landed == True."""
    return bool(readings.landed) and readings.landed[-1].value is True


def find_position_gaps(
    positions: Sequence[TimedVec3],
    max_gap_s: float,
) -> list[tuple[float, float]]:
    """Return (t_prev, t_next) intervals where position samples exceed max_gap_s."""
    gaps: list[tuple[float, float]] = []
    for prev, curr in zip(positions, positions[1:], strict=False):
        if (curr.t_s - prev.t_s) > (max_gap_s + EPS):
            gaps.append((prev.t_s, curr.t_s))
    return gaps


def missing_topics_for(
    readings: Readings,
    config: VerifierConfig,
    reading_names: Sequence[str],
    *,
    ignore_readings: set[str] | frozenset[str] = frozenset({"camera_triggered_at"}),
) -> list[str]:
    """Return missing log topics needed by any reading in reading_names."""
    if not readings.missing_topics:
        return []
    topic_map = (
        config.log_only_reading_topics
        if readings.sources == "log only" or readings.sources is None
        else config.recorded_reading_topics
    )
    missing_set = set(readings.missing_topics)
    found: list[str] = []
    for name in reading_names:
        if name in ignore_readings:
            continue
        topic = topic_map.get(name)
        if topic and topic in missing_set and topic not in found:
            found.append(topic)
    return found
