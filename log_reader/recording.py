"""Read the harness's recording of Gazebo's pose topic (gz_pose.jsonl).

One JSON object per line:
  {"k": "pose", "t": sim seconds, "p": [east, north, up]}   the vehicle's position
  {"k": "pubs", "pubs": [[address, type], ...]}   the topic's publishers, on each change
  {"k": "info", ...}   recorder notes, maybe an `error`

Gazebo's world frame is east, north, up (ENU), so `p` is in that order. The recording's
clock is the sim clock, which in SITL lockstep is also PX4's clock: t * 1e6 is a log
timestamp in microseconds, with no offset.
"""

import json
import math

# Where each named direction sits in a pose line's "p" list.
P_INDEX = {"east": 0, "north": 1, "up": 2}


class Recording:
    """The pose samples, the topic's publishers, and anything that makes it unusable."""

    def __init__(self, path):
        self.samples = []  # [(timestamp_us, east, north, up), ...] in time order
        self.publishers = set()  # every publisher address any pubs line listed
        self.listed_publishers = False  # did any pubs line list them at all?
        self.problem = None  # why the recording can't be used, or None
        if path is None:
            self.problem = "run.json names no recording file"
            return
        if not path.is_file():
            self.problem = f"the recording {path.name} is missing"
            return
        self._read(path)
        if self.problem is None and not self.samples:
            self.problem = f"the recording {path.name} has no pose samples"

    def _read(self, path):
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        seen = set()
        for number, line in enumerate(lines, start=1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                if number == len(lines):
                    break  # a last line cut off mid-write (the recorder was stopped)
                self.problem = f"line {number} of {path.name} isn't JSON"
                return
            if not isinstance(entry, dict):
                self.problem = f"line {number} of {path.name} isn't a JSON object"
                return
            kind = entry.get("k")
            if kind == "pose":
                sample = _pose(entry)
                if sample is None:
                    self.problem = f"line {number} of {path.name} isn't a usable pose"
                    return
                if sample[0] in seen:
                    continue  # the same sim instant twice: keep the first
                seen.add(sample[0])
                self.samples.append(sample)
            elif kind == "pubs":
                self._publishers(entry.get("pubs") or [])
            elif kind == "info" and "error" in entry:
                self.problem = f"the recorder reported an error: {entry['error']}"
                return
        self.samples.sort()

    def _publishers(self, pubs):
        self.listed_publishers = True
        for pub in pubs:
            if pub and pub[0] == "error":
                # The recorder couldn't ask Gazebo who publishes: we can't tell.
                self.problem = f"the recorder couldn't list the publishers: {pub[1:]}"
                return
            self.publishers.add(pub[0])

    def times(self):
        return [sample[0] for sample in self.samples]

    def value(self, sample, direction):
        """One direction (east, north or up) of one sample."""
        return sample[1 + P_INDEX[direction]]


def _pose(entry):
    """(timestamp_us, east, north, up) from a pose line, or None if it isn't one."""
    t, p = entry.get("t"), entry.get("p")
    if not isinstance(t, int | float) or not isinstance(p, list) or len(p) != 3:
        return None
    if not all(isinstance(v, int | float) and math.isfinite(v) for v in (t, *p)):
        return None
    return (round(t * 1e6), *p)  # sim seconds -> microseconds
