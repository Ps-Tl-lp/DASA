"""Check the log's own copy of the drone's position against Gazebo's recording.

PX4's gz_bridge reads the same Gazebo topic the harness records and logs it as
vehicle_local_position_groundtruth, in north, east, down. So in a correct run every
log sample has a recorded sample at the same sim time, at the same place. The only
difference is PX4 storing the numbers as 32-bit floats: micrometres. A log that
disagrees is invalid evidence, so the run is INCONCLUSIVE. This is the config's
`cross_check` section.
"""

import bisect
import math

PASS, INCONCLUSIVE = "PASS", "INCONCLUSIVE"


def cross_check(
    log, recording, recording_name, section, time_within_s, max_difference_m
):
    """The `cross_check` entry of readings.json, as a dict.

    section: the config's cross_check section (which log topic, and which of its fields
    is north, east and down). time_within_s, max_difference_m: the tolerances it names.
    """
    names = section["log"]
    topic = names["topic"]
    north = log.series(topic, names["north"])
    east = log.series(topic, names["east"])
    down = log.series(topic, names["down"])
    result = {
        "recording": recording_name,
        "compared": 0,
        "unmatched": 0,
        "over_limit": 0,
        "max_difference_m": None,
        "publishers": len(recording.publishers)
        if recording.listed_publishers
        else None,
        "verdict": INCONCLUSIVE,
        "reason": "",
    }

    if recording.problem:
        result["unmatched"] = len(north)
        result["reason"] = recording.problem
        return result
    if not north:
        result["reason"] = f"the log has no {topic}"
        return result

    times = recording.times()
    window_us = time_within_s * 1e6
    largest = 0.0
    for (t_us, x), (_, y), (_, z) in zip(north, east, down, strict=True):
        sample = _nearest(recording, times, t_us)
        if abs(sample[0] - t_us) > window_us:
            result["unmatched"] += 1  # no recorded sample at this sim time
            continue
        result["compared"] += 1
        # The log is north, east, down; the recording is east, north, up.
        difference = math.dist(
            (x, y, z),
            (
                recording.value(sample, "north"),
                recording.value(sample, "east"),
                -recording.value(sample, "up"),
            ),
        )
        # "Not within the limit" rather than "over it": a NaN in the log is never
        # within anything, so it counts against the log instead of slipping through.
        if not difference <= max_difference_m:
            result["over_limit"] += 1
        if math.isfinite(difference):
            largest = max(largest, difference)
    result["max_difference_m"] = largest

    total = len(north)
    if result["unmatched"]:
        result["reason"] = (
            f"{result['unmatched']} of {total} log samples have no recorded sample "
            f"within {time_within_s * 1000:g} ms"
        )
    elif result["over_limit"]:
        result["reason"] = (
            f"{result['over_limit']} of {total} log samples are not within "
            f"{max_difference_m:g} m of the recording"
        )
    elif result["publishers"] is None:
        result["reason"] = "the recording never listed the pose topic's publishers"
    elif result["publishers"] != 1:
        result["reason"] = (
            f"the pose topic had {result['publishers']} publishers, not 1, so the "
            "recording may not be the simulator's"
        )
    else:
        result["verdict"] = PASS
        result["reason"] = (
            f"all {total} log samples match Gazebo's recording; "
            f"largest difference {largest * 1e6:.1f} um"
        )
    return result


def _nearest(recording, times, t_us):
    """The recorded sample closest in time to t_us (times is sorted)."""
    i = bisect.bisect_left(times, t_us)
    candidates = [j for j in (i - 1, i) if 0 <= j < len(times)]
    j = min(candidates, key=lambda k: abs(times[k] - t_us))
    return recording.samples[j]
