"""Turn one run's log (and Gazebo recording, if it has one) into readings.json.

The rows come from platform_configs/px4.yaml:
  readings           a run whose run.json names a `recording`: position, velocity and
                     landed from Gazebo's recording, the rest from the log
  log_only_readings  a run with no `recording` key (flown before the harness recorded):
                     everything from the log

Each row is one reading, a list of timed values over the flight. The kinds of row:
  {source: log, topic, field}       every sample of that field in the log
  {source: log, parameter}          one value: the parameter at the start of the log
  {source: gz_pose, field}          the recording's north, east or up
  {source: gz_pose, rate_of}        velocity, worked out from another reading
  {source: gz_pose, on_ground_m, still_below_m_s}
                                    landed, worked out from height and speed
plus `subtract_first` (measure from the first value) and `flip_sign` (multiply by -1).
"""

import json
import math
from pathlib import Path

import yaml

from .cross_check import INCONCLUSIVE, PASS, cross_check
from .recording import Recording
from .ulog import Log, MissingField

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "platform_configs" / "px4.yaml"

# readings.json groups the config's readings (tests/fixtures/m01/README.md, formats).
GROUPS = {
    "position": ("agent.x", "agent.y", "agent.z"),
    "velocity": ("agent.velocity.x", "agent.velocity.y", "agent.velocity.z"),
}
OUTPUT_NAMES = {"agent.landed": "landed"}  # every other reading keeps its config name

TIME_DECIMALS, VALUE_DECIMALS = 3, 4  # the File formats' rounding


class ReaderError(Exception):
    """The run can't be read: no log, no time zero, or a field the config names is
    missing from the log."""


def load_config(path=DEFAULT_CONFIG):
    with open(path) as f:
        return yaml.safe_load(f)


def follow(config, name):
    """The value a config name points to: `tolerances.landed.height_m` -> 0.1."""
    node = config
    for part in name.split("."):
        node = node[part]
    return node


def read_run(run_folder, config=None):
    """readings.json for one run folder (the one holding its run.json), as a dict."""
    config = config or load_config()
    run_folder = Path(run_folder)
    run = json.loads((run_folder / "run.json").read_text())
    if not run.get("log"):
        raise ReaderError("run.json names no log to read")

    recorded = "recording" in run  # a harness that records always writes this key
    rows = config["readings" if recorded else "log_only_readings"]
    section = config["cross_check"]
    topics = {row["topic"] for row in rows.values() if "topic" in row}
    topics |= set(config["time_zero_topics"])
    if recorded:
        topics.add(section["log"]["topic"])

    log = Log(run_folder / run["log"], topics)
    time_zero_us = _time_zero(log, config["time_zero_topics"])
    needed = {row["topic"] for row in rows.values() if "topic" in row}
    if recorded:
        needed.add(section["log"]["topic"])  # the cross-check and the span need it
    missing_topics = sorted(t for t in needed if not log.has(t))

    readings = {}  # reading name -> [(t_us, value)], or one value for a parameter
    cross = None
    try:
        for name, row in rows.items():
            if row["source"] == "log":
                readings[name] = _log_reading(log, row)
        if recorded:
            # A null `recording` is still a recorded run, just one without a file.
            name = run["recording"]
            recording = Recording(run_folder / name if name else None)
            cross = cross_check(
                log,
                recording,
                name,
                section,
                follow(config, section["same_time_within_s"]),
                follow(config, section["max_difference_m"]),
            )
            span = _log_span(log, section["log"]["topic"])
            usable = recording.problem is None and span is not None
            readings.update(_recording_readings(config, rows, recording, span, usable))
    except MissingField as error:
        raise ReaderError(str(error)) from error

    if log.problem and cross is not None:
        # Samples that survived the damage can still match the recording, but they
        # can't vouch for the part pyulog skipped.
        reason = f"{log.problem}, so it can't be checked against the recording"
        if cross["verdict"] != PASS:
            reason += f"; {cross['reason']}"
        cross.update(verdict=INCONCLUSIVE, reason=reason)

    return _assemble(
        run, rows, readings, missing_topics, time_zero_us, recorded, cross, log.problem
    )


# ---- Log rows ------------------------------------------------------------------------


def _log_reading(log, row):
    if "parameter" in row:
        return log.parameters.get(row["parameter"])  # None if the log didn't record it
    series = log.series(row["topic"], row["field"])
    if row.get("subtract_first") and series:
        first = series[0][1]
        series = [(t, v - first) for t, v in series]
    if row.get("flip_sign"):
        series = [(t, -v) for t, v in series]
    return series


def _time_zero(log, topics):
    """The earliest sample of any of `topics` that the log has: reading time 0."""
    firsts = [log.timestamps(t)[0] for t in topics if log.timestamps(t)]
    if not firsts:
        raise ReaderError(f"the log has none of {', '.join(topics)}")
    return min(firsts)


def _log_span(log, topic):
    """The log's own span: its first to last ground-truth sample, or None."""
    times = log.timestamps(topic)
    return (times[0], times[-1]) if times else None


# ---- Recording rows ------------------------------------------------------------------


def _recording_readings(config, rows, recording, span, usable):
    """The gz_pose rows. Empty lists if the recording can't be used (the cross-check
    already says why, and makes the run INCONCLUSIVE)."""
    gz = {name: row for name, row in rows.items() if row["source"] == "gz_pose"}
    if not usable:
        return {name: [] for name in gz}

    # The readings cover the log's span, so a log cut short gives readings cut short.
    start, end = span
    window = follow(config, config["cross_check"]["same_time_within_s"]) * 1e6
    samples = [s for s in recording.samples if start - window <= s[0] <= end + window]
    # subtract_first measures from the recording's sample at the log's first
    # ground-truth sample: where the drone sat before takeoff. A recording that started
    # later has no such sample, and any later one could already be in the air, so there
    # are no positions at all. The cross-check counts the missing samples, so the run is
    # INCONCLUSIVE anyway.
    if not samples or abs(samples[0][0] - start) > window:
        return {name: [] for name in gz}

    out = {}
    # Positions first: north, east or up of each sample.
    for name, row in gz.items():
        if "field" in row:
            series = [(s[0], recording.value(s, row["field"])) for s in samples]
            if row.get("subtract_first"):
                first = series[0][1]
                series = [(t, v - first) for t, v in series]
            out[name] = series
    # Then velocities, from the positions.
    for name, row in gz.items():
        if "rate_of" in row:
            out[name] = rate_of(out[row["rate_of"]])
    # Then landed, from height and speed.
    for name, row in gz.items():
        if "on_ground_m" in row:
            height = next(out[n] for n, r in gz.items() if r.get("field") == "up")
            speeds = [out[n] for n, r in gz.items() if "rate_of" in r]
            out[name] = landed(
                height,
                speeds,
                follow(config, row["on_ground_m"]),
                follow(config, row["still_below_m_s"]),
            )
    return out


def rate_of(series):
    """Velocity at each reading: the change since the reading before, over the time
    between them (a backward difference). The first reading's velocity is 0."""
    out = []
    for i, (t, value) in enumerate(series):
        if i == 0:
            out.append((t, 0.0))
            continue
        t_before, value_before = series[i - 1]
        out.append((t, (value - value_before) / ((t - t_before) / 1e6)))
    return out


def landed(height, speeds, on_ground_m, still_below_m_s):
    """Landed at a reading: no higher than on_ground_m above the start, and slower than
    still_below_m_s overall (the speed across all three directions)."""
    out = []
    for i, (t, z) in enumerate(height):
        speed = math.sqrt(sum(series[i][1] ** 2 for series in speeds))
        out.append((t, z <= on_ground_m and speed < still_below_m_s))
    return out


# ---- readings.json -------------------------------------------------------------------


def _assemble(
    run, rows, readings, missing_topics, time_zero_us, recorded, cross, log_problem
):
    out = {key: run[key] for key in ("mission_id", "run_id", "run_status")}
    if run.get("reason"):
        out["reason"] = run["reason"]

    record = run.get("record")
    if isinstance(record, dict):
        setup = {
            key: record[key]
            for key in ("px4_commit", "simulator", "speed")
            if key in record
        }
        if setup:
            out["record"] = setup

    def seconds(t_us):
        return round((t_us - time_zero_us) / 1e6, TIME_DECIMALS)

    def number(value):
        if not math.isfinite(value):
            return None  # JSON has no NaN; null says "no usable value here"
        return round(value, VALUE_DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0

    grouped = {name for names in GROUPS.values() for name in names}
    for group, (nx, ny, nz) in GROUPS.items():
        xs, ys, zs = readings[nx], readings[ny], readings[nz]
        out[group] = [
            {"t_s": seconds(t), "x": number(x), "y": number(y), "z": number(z)}
            for (t, x), (_, y), (_, z) in zip(xs, ys, zs, strict=True)
        ]
    for name, row in rows.items():
        if name in grouped:
            continue
        value = readings[name]
        key = OUTPUT_NAMES.get(name, name)
        if "parameter" in row:
            out[key] = value
        elif row.get("field") == "timestamp":
            out[key] = [{"t_s": seconds(t)} for t, _ in value]  # events: just the times
        else:
            out[key] = [{"t_s": seconds(t), "value": v} for t, v in value]

    if log_problem:
        out["log_problem"] = log_problem
    out["missing_topics"] = missing_topics
    out["sources"] = (
        {name: row["source"] for name, row in rows.items()} if recorded else "log only"
    )
    out["time_zero_us"] = time_zero_us
    if cross is not None:
        out["cross_check"] = cross
    return out


def readings_text(readings):
    """readings.json's text, laid out like the fixture: one line per timed value."""
    lines = ["{"]
    items = list(readings.items())
    for index, (key, value) in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        if isinstance(value, list) and value and isinstance(value[0], dict):
            inner = ",\n".join(f"    {json.dumps(v, allow_nan=False)}" for v in value)
            lines.append(f'  "{key}": [\n{inner}\n  ]{comma}')
        else:
            lines.append(f'  "{key}": {json.dumps(value, allow_nan=False)}{comma}')
    lines.append("}")
    return "\n".join(lines) + "\n"
