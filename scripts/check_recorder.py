"""Local Gazebo Transport smoke test. No simulator or aircraft is started."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


def main():
    os.environ["GZ_PARTITION"] = "hydra_probe_" + uuid.uuid4().hex
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.transport13 import Node

    with tempfile.TemporaryDirectory(prefix="hydra-recorder-check-") as directory:
        folder = Path(directory)
        topic = "/world/hydra_probe/pose/info"
        node = Node()
        publisher = node.advertise(topic, Pose_V)
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("gz_recorder.py")),
                "--topic",
                topic,
                "--model",
                "x500_0",
                "--output",
                str(folder / "pose.jsonl"),
                "--ready",
                str(folder / "ready"),
            ]
        )
        try:
            deadline = time.monotonic() + 15
            while not (folder / "ready").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("recorder failed to become ready")
                time.sleep(0.1)
            message = Pose_V()
            message.header.stamp.sec = 12
            message.header.stamp.nsec = 250000000
            pose = message.pose.add()
            pose.name = "x500_0"
            pose.position.x, pose.position.y, pose.position.z = 2, 3, 4
            for _ in range(50):
                publisher.publish(message)
                time.sleep(0.1)
        finally:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        rows = [
            json.loads(line)
            for line in (folder / "pose.jsonl").read_text().splitlines()
        ]
        poses = [row for row in rows if row["k"] == "pose"]
        assert process.returncode == 0
        assert poses and all(
            row["t"] == 12.25 and row["p"] == [2, 3, 4] for row in poses
        )
        assert any(row["k"] == "pubs" and row["pubs"] for row in rows)
        assert not any(row.get("error") for row in rows)
        print(
            f"Recorder smoke test passed: {len(poses)} poses, "
            "clock, ENU and publisher metadata"
        )


if __name__ == "__main__":
    main()
