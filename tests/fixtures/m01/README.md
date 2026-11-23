# M01 test fixture

One mission and two runs of it, so each piece of the pipeline can be built and tested before the pieces connect.

M01: fly to W1 (50 m north of the base, 20 m up), stay there 5 s, land back at the base.

| Run | Readings from | Time at W1 | Verdict |
|---|---|---|---|
| R01 (this folder) | made up by hand | 2.55 s while PX4 flew the mission (3.40 s counting the return) | FAIL, hold too short |
| R02 (`R02/`) | a real Gazebo flight of `mission.plan` | 5.03 s while PX4 flew the mission (6.11 s counting the return) | PASS |

A verifier should get both right.

## Files

| File | Made by | Read by |
|---|---|---|
| `simple.yaml` | written by hand | generator |
| `mission.yaml`, `start.xml`, `goal.xml` | generator | plan step, verifier |
| `mission.plan` | plan step | harness |
| `run.json` | harness | log reader |
| `readings.json` | log reader | verifier |
| `expected-verdict.json` | the answer the verifier should give | |

Each run has its own `run.json`, `readings.json` and `expected-verdict.json`. Both use the same mission files.

`readings.json` groups the config's readings. `position` is `agent.x`, `agent.y` and `agent.z`. `velocity` is `agent.velocity.x`, `.y` and `.z`. `landed` is `agent.landed`. `nav_state` (PX4's flight mode; 3 is mission mode) and `disarm_reason` are the readings of those names. The file formats are a first guess. Change them if they don't work for you.

The zone and tolerances come from `platform_configs/px4.yaml`. R02's log (`R02.ulg`) is not in the repo, because raw logs stay out of git.

## How the verdicts were worked out

- **Hold** (`hold_at` in `platform_configs/px4.yaml`): the longest stretch inside the zone while PX4 is in mission mode, from the first such reading to the first later reading that is outside the zone or not in mission mode. It may be up to `hold_short_by_s` (0.25 s) short of the mission's 5 s.
  - **R01:** enters at 12.00 s. PX4 switches to the return at 14.55 s, while the drone is still in the zone (it leaves at 15.40 s): 2.55 s, FAIL. Counting the return, as the old rule did, gives 3.40 s, still FAIL; a verifier that ignores the flight mode gets 3.40 s and so the wrong `observed_s`.
  - **R02:** enters at 37.184 s. PX4 leaves mission mode at 42.152 s, and the first reading after that is at 42.216 s: 5.03 s, PASS. The time the return took to climb out of the zone no longer counts: under the old rule R02 read 6.11 s. An earlier note here gave 4.97 s, measured to the switch time instead of the first reading after it.
- **`disarmed_after_landing`** (every mission gets it): the disarm reason changes to 6 at or after touchdown, and to nothing else after takeoff. Touchdown is the first landed reading after the last airborne one.
  - **R01:** touchdown at 24.00 s, and the reason changes to 6 at 26.00 s. PASS. The 2.00 s is made up: in real flights PX4 disarms about 3 s after a touchdown worked out from position, which is 2 s (`COM_DISARM_LAND`) after its own land detector.
  - **R02:** touchdown at 85.376 s, and the reason changes to 6 at 87.392 s. PASS.
- **`goal_check`:** the last readings match the goal state: within 0.5 m of the base, landed, and slower than 0.1 m/s.
- **`visited`:** any reading inside the zone.

The expected values were worked out from the readings by hand, not taken from a verifier.

## Where the runs came from

- **R01:** written by hand. No simulator and no log. One sample every 0.05 s. Its flight mode and disarm reason are made up too, as PX4 would publish them on a change: mission mode (3) from 0.5 s, return (5) from 14.55 s, as the drone starts back while still at W1, and the disarm (reason 6) at 26.00 s, 2 s after touchdown.
- **R02:** one of my local Gazebo runs, not a shared team run.
  - PX4 build `fca3df865a` (the build the repo pins, ADR 0001), SITL with Gazebo, model `gz_x500`, sim speed 4x
  - Plan flown: `mission.plan` in this folder
  - Readings: every sample of `vehicle_local_position_groundtruth` (position and velocity), `vehicle_land_detected` (landed) and `vehicle_status` (`nav_state` and `latest_disarming_reason`), read with `log_only_readings` in `platform_configs/px4.yaml`. R02 was flown before the harness recorded Gazebo's pose, so it is read from the log alone, and its `landed` is PX4's land detector. Nothing was trimmed. Times are seconds from the earliest sample of those two topics. Positions and velocities are rounded to four decimals.
  - Log: `R02.ulg`, md5 `6e43a1b089e2b3d364321ccc2b04480c`. It is only on my machine for now. Checking a verifier against these readings works today; re-reading the log is not something a teammate can repeat yet.

