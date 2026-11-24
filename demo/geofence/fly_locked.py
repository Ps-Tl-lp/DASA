"""Run one mission through the whole pipeline (scripts/run_mission.py), one flight at
a time on this machine.

Takes a flight lock and waits for any PX4 or Gazebo already running, so it never
flies on top of another run. The lock is HYDRA_FLIGHT_LOCK if set (point it at any
other tool's lock to share it), else runs/.harness.lock.
"""

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

LOCK = Path(os.environ.get("HYDRA_FLIGHT_LOCK", "runs/.harness.lock"))
SIMS = "build/px4_sitl_default/bin/px4|gz sim"

LOCK.parent.mkdir(parents=True, exist_ok=True)
with open(LOCK, "a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    while subprocess.run(["pgrep", "-f", SIMS], capture_output=True).returncode == 0:
        time.sleep(2)
    runner = [sys.executable, "scripts/run_mission.py", *sys.argv[1:]]
    sys.exit(subprocess.call(runner))
