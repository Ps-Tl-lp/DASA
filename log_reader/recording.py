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
        self.lookup_failed = (
            False  # did the recorder fail to ask Gazebo, at least once?
        )
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
        try:
            data = path.read_bytes()
        except OSError as error:
            reason = error.strerror or error
            self.problem = f"the recording {path.name} can't be read: {reason}"
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            self.problem = (
                f"the recording {path.name} isn't UTF-8 text (byte {error.start})"
            )
            return
        # A line followed by a newline was written in full. Only a last line with no
        # newline after it can be a write the recorder didn't finish when it stopped.
        lines = text.split("\n")
        seen = {}  # timestamp_us -> the pose first recorded at that sim instant
        for number, line in enumerate(lines, start=1):  # numbered as in the file
            if not line.strip():
                continue
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
                    if seen[sample[0]] != sample[1:]:
                        # One model can't be in two places at one sim instant: a
                        # second publisher, or a recording that was edited.
                        self.problem = (
                            f"line {number} of {path.name} gives a second, different "
                            f"pose at t = {entry['t']} s"
                        )
                        return
                    continue  # the same pose at the same sim instant again: keep one
                seen[sample[0]] = sample[1:]
                self.samples.append(sample)
            elif kind == "pubs":
                if not self._publishers(entry.get("pubs")):
                    self.problem = (
                        f"line {number} of {path.name} isn't a publisher list"
                    )
                    return
            elif kind == "info" and "error" in entry:
                self.problem = f"the recorder reported an error: {entry['error']}"
                return
        self.samples.sort()

    def _publishers(self, pubs):
        """Add one pubs line's publishers. False unless it is [[address, type], ...]."""
        if not isinstance(pubs, list):
            return False
        for pub in pubs:
            if not (
                isinstance(pub, list)
                and len(pub) == 2
                and all(isinstance(part, str) for part in pub)
            ):
                return False  # each entry is [address, type]
            if pub[0] == "error":
                # The recorder couldn't ask Gazebo who publishes, this time. The poses
                # are still good, but a second publisher can't be ruled out.
                self.lookup_failed = True
                continue
            self.listed_publishers = True
            self.publishers.add(pub[0])
        return True

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
