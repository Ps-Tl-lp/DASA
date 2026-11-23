"""Read the harness's recording of Gazebo's pose topic (gz_pose.jsonl).

One JSON object per line:
  {"k": "pose", "t": sim seconds, "p": [east, north, up]}   the vehicle's position
  {"k": "pubs", "pubs": [[address, type], ...]}   who publishes the pose topic
  {"k": "info", ...}   recorder notes, maybe an `error`

Gazebo's world frame is east, north, up (ENU), so `p` is in that order. The recording's
clock is the sim clock, which in SITL lockstep is also PX4's clock: t * 1e6 is a log
timestamp in microseconds, with no offset.
"""

import json

# Where each named direction sits in a pose line's "p" list.
P_INDEX = {"east": 0, "north": 1, "up": 2}


class Recording:
    """The pose samples, the topic's publishers, and anything that makes it unusable."""

    def __init__(self, path):
        self.samples = []  # [(timestamp_us, east, north, up), ...] in time order
        self.publishers = None  # the last "pubs" line's list, or None if there was none
        self.problem = None  # why the recording can't be used, or None
        if not path.is_file():
            self.problem = f"the recording {path.name} is missing"
            return

        seen = set()
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                self.problem = f"line {number} of {path.name} isn't JSON"
                return
            kind = entry.get("k")
            if kind == "pose":
                t_us = round(entry["t"] * 1e6)  # sim seconds -> microseconds
                if t_us in seen:
                    continue  # the same sim instant twice: keep the first
                seen.add(t_us)
                self.samples.append((t_us, *entry["p"]))
            elif kind == "pubs":
                self.publishers = entry["pubs"]
            elif kind == "info" and "error" in entry:
                self.problem = f"the recorder reported an error: {entry['error']}"
        self.samples.sort()
        if self.problem is None and not self.samples:
            self.problem = f"the recording {path.name} has no pose samples"

    def times(self):
        return [sample[0] for sample in self.samples]

    def value(self, sample, direction):
        """One direction (east, north or up) of one sample."""
        return sample[1 + P_INDEX[direction]]
