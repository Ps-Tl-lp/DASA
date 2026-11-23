# M01 test fixture

One mission and two runs of it, so each piece of the pipeline can be built and tested before the pieces connect.

M01: fly to W1 (50 m north of the base, 20 m up), stay there 5 s, land back at the base.

| Run | Readings from | Time at W1 | Verdict |
|---|---|---|---|
| R01 (this folder) | made up by hand | 3.40 s | FAIL, hold too short |
| R02 (`R02/`) | a real Gazebo flight of `mission.plan` | 6.11 s | PASS |

A verifier should get both right.

## Files

| File | Made by | Read by |
|---|---|---|
| `simple.yaml` | written by hand | generator |
| `mission.yaml`, `start.xml`, `goal.xml` | generator | plan translator, verifier |
| `mission.plan` | plan translator | harness |
| `run.json` | harness | log reader |
| `readings.json` | log reader | verifier |
| `expected-verdict.json` | the answer the verifier should give | |

Each run has its own `run.json`, `readings.json` and `expected-verdict.json`. Both use the same mission files. The file formats are a first guess. Change them if they don't work for you.

The zone and tolerances come from `platform_configs/px4.yaml`. R02's log (`R02.ulg`) is not in the repo, because raw logs stay out of git.

## How the verdicts were worked out

- **Hold:** the time at W1 from the first reading inside the zone to the first reading outside it. The return climb counts. R02 is at W1 for 4.97 s before PX4 leaves mission mode for the return, and 6.11 s in all, so its PASS depends on that.
- **`landed_at_base`:** the last readings are within 0.5 m of the base, landed, and slower than 0.1 m/s.
- **`visited`:** any reading inside the zone.

## Where the runs came from

- **R01:** written by hand. No simulator and no log. One sample every 0.05 s.
- **R02:** one of my local Gazebo runs, not a shared team run.
  - PX4 build `fca3df865a` (the build the repo pins, ADR 0001), SITL with Gazebo, model `gz_x500`, sim speed 4x
  - Plan flown: `mission.plan` in this folder
  - Readings: every sample of `vehicle_local_position_groundtruth` (position and velocity) and `vehicle_land_detected` (landed), read with the mappings in `platform_configs/px4.yaml`. Nothing was trimmed. Times are seconds from the earliest sample of those two topics. Positions and velocities are rounded to four decimals.
  - Log: `R02.ulg`, md5 `6e43a1b089e2b3d364321ccc2b04480c`. It is only on my machine for now. Checking a verifier against these readings works today; re-reading the log is not something a teammate can repeat yet.

