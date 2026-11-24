"""Gazebo Harmonic model-pose recorder, independent of PX4's log writer."""

import argparse
import json
import math
import signal
import subprocess
import threading
import time
from pathlib import Path


class PoseWriter:
    def __init__(self, stream, model):
        self.stream = stream
        self.model = model
        self.lock = threading.Lock()
        self.samples = 0
        self.last_wall = None
        self.error = None

    def write(self, row):
        with self.lock:
            self.stream.write(json.dumps(row, allow_nan=False) + "\n")
            self.stream.flush()

    def receive(self, message):
        try:
            matches = [p for p in message.pose if p.name == self.model]
            if len(matches) != 1:
                return
            p = matches[0].position
            values = [p.x, p.y, p.z]
            stamp = message.header.stamp
            seconds = stamp.sec + stamp.nsec / 1_000_000_000
            if not all(math.isfinite(v) for v in [seconds, *values]):
                raise ValueError("nonfinite pose or timestamp")
            self.write({"k": "pose", "t": seconds, "p": values})
            self.samples += 1
            self.last_wall = time.monotonic()
        except Exception as exc:
            self.error = str(exc)


def publishers(node, topic):
    # The Harmonic Python binding exposes message type but omits publisher addr.
    # The installed CLI uses the same discovery API and includes the addresses.
    result = subprocess.run(
        ["gz", "topic", "-i", "-t", topic],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("tcp://") and ", " in line:
            rows.append(line.split(", ", 1))
    return sorted(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ready", required=True, type=Path)
    args = parser.parse_args()
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.transport13 import Node

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    node = Node()
    with args.output.open("x", encoding="utf-8") as stream:
        writer = PoseWriter(stream, args.model)
        writer.write({"k": "info", "topic": args.topic, "model": args.model})
        node.subscribe(Pose_V, args.topic, writer.receive)
        # Readiness means subscription installed, even before the world/model exists.
        args.ready.touch(exist_ok=False)
        previous = None
        try:
            while not stop.is_set():
                current = publishers(node, args.topic)
                if current != previous:
                    writer.write({"k": "pubs", "pubs": current})
                    previous = current
                if writer.error:
                    raise RuntimeError(writer.error)
                stop.wait(1)
        except Exception as exc:
            writer.write({"k": "info", "error": str(exc)})
            raise
        finally:
            node.unsubscribe(args.topic)
            writer.write({"k": "info", "samples": writer.samples, "stopped": True})


if __name__ == "__main__":
    main()
