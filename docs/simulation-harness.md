# Simulation harness

Run in Ubuntu/WSL with Gazebo Harmonic, a built PX4 checkout matching
`sim.px4_build`, PyYAML, pymavlink and the Gazebo Python bindings
`gz.transport13` and `gz.msgs10`. These are simulator runtime prerequisites,
not new CI dependencies. The recorder subscribes before PX4 starts and writes
the selected model's raw ENU pose at simulator time. PX4 starts Gazebo using
its own startup scripts. All Gazebo discovery uses a fresh partition.

From the repository root:

```sh
python3 scripts/run_simulation.py \
  --plan tests/fixtures/m01/mission.plan \
  --start tests/fixtures/m01/start.xml \
  --config platform_configs/px4.yaml \
  --px4 /path/to/PX4-Autopilot \
  --mission-id M01 --run-id R003 --output runs/M01/R003
```

The output directory must not exist. The runner preserves the plan, start state
and platform config, `run.json`, `gz_pose.jsonl`, `flight.ulg` when available,
events and console output. `px4-gazebo-output.log` contains both simulator and
PX4 startup output. The temporary Linux PX4 working directory is retained and
its path recorded in harness-events.jsonl, including on failure. Remove it only
after reviewing and preserving needed evidence.

The command exits 0 for completed execution and 2 for inconclusive execution.
Neither exit code is a mission verdict. The 300-second configured timeout is
wall-clock time from confirmed armed Mission-mode execution until disarm.
Timeout writes `run_status: inconclusive`, `reason: timeout`. It sends no RTL
or disarm recovery command. Cleanup stops only the process groups created for
this run. Interrupted runs keep partial evidence. Reusing an output directory
fails rather than replacing evidence.

New attempts always name `recording: gz_pose.jsonl`, even if setup or recording
fails. The log reader must reject missing, short or mismatching recordings.
The runner records the actual PX4 commit and rejects a checkout that differs
from the config's baseline. It does not fetch, rebuild or change PX4.

The MAVLink endpoint is local UDP port 14540, system/component 1/1. Run one
harness at a time and stop other SITL instances first. The current runner supports
SimpleItems for takeoff, goto, RTL and camera trigger in frames 0, 2 and 3.
The supplied plan must already have passed the plan step. Rally points, uploaded
PX4 geofences and paused mission items are rejected.

The documented parameter writes are acknowledged and checked against readback.
Mission upload is acknowledged after every requested item has been sent. Ordinary
arming retries allow sensors to initialize, with a bounded setup timeout. There
is no force-arm. Missing telemetry or process failure preserves an inconclusive
record and diagnostic reason. The landing/disarm correctness check belongs to
the verifier.

Validation sequence: run the unit tests, test recorder subscription with a local
Pose_V publisher, fly M01 on the pinned build, then give run.json to the team's
log reader. Confirm full recording coverage and matching clocks before judging
the flight. Finally connect a generated mission. Full baseline-flight validation
requires the pinned build and the log reader, which are separate prerequisites.

Run the recorder-only smoke test with `python3 scripts/check_recorder.py`.
It starts a synthetic Gazebo Transport publisher in a fresh partition and checks
the actual recorder subprocess, timestamps, coordinates and publisher discovery.
It does not start PX4 or fly a mission.

Known trust limitation: the recorder is a separate process in the same host
account as PX4. This is not container isolation against malicious variants.
