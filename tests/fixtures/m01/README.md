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
| `simple.yaml` | written by hand | generator, plan step, verifier |
| `start.xml`, `goal.xml` | generator | plan step, verifier |
| `mission.plan` | plan step | harness |
| `run.json` | harness | log reader |
| `readings.json` | log reader | verifier |
| `expected-verdict.json` | the answer the verifier should give | |

Each run has its own `run.json`, `readings.json` and `expected-verdict.json`. Both use the same `simple.yaml`, `start.xml` and `goal.xml`. The five-second hold comes from `simple.yaml`.

`readings.json` groups the config's readings. `position` is `agent.x`, `agent.y` and `agent.z`. `velocity` is `agent.velocity.x`, `.y` and `.z`. `landed` is `agent.landed`. `nav_state` (PX4's flight mode; 3 is mission mode), `disarm_reason` and `arming_state` (1 disarmed, 2 armed) are the readings of those names. The formats are below.

The zone and tolerances come from `platform_configs/px4.yaml`. R02's log (`R02.ulg`) is not in the repo, because raw logs stay out of git.

## File formats

Times are in seconds, positions in metres from the base (x north, y east, z up) and speeds in m/s. Lists of timed values are sorted by time. Later these sections become JSON Schema files, each with a `fileType` and an integer `version`, rejecting unknown keys and changing only by adding.

**`simple.yaml`** is the settings file used to generate M01. The plan step and verifier read it alongside `start.xml` and `goal.xml`.
- `mission_id` ties these settings to the run records. For this fixture it is `M01`.
- `waypoints` and `goal` say how many waypoints to create and where the drone should finish.
- `postconditions.hold_at_each_waypoint.min_s` sets the hold time for each waypoint. Here it is five seconds at W1. The plan step uses that time to build the plan, and the verifier uses it to check the readings.

**`start.xml`, `goal.xml`:** every property of the base, the agent and each waypoint, with its type and unit:
- **Base:** `x`, `y`, `z`.
- **Agent:** `x`, `y`, `z`; `velocity` with its own `x`, `y`, `z`; `landed`, `vehicle_type`, `has_camera`, `has_grippers`.
- **Each waypoint:** `x`, `y`, `z`, `visited`, and `clicked_pic`. A waypoint that doesn't list `clicked_pic` counts as false.

The environment file on the `env-rep` branch (`docs/environment/environment_representation.xml`) has more properties than these (`no_fly_zone`, `dwell_time`, `visited_at`, `under_range`, `is_carrying`, `was_attacked`, `has_package`). The config doesn't use them.

**`run.json`**
- **Which run:** `mission_id`, `run_id`, and `plan` (the `.plan` file's path, from the run folder).
- **`run_status`:** `completed` or `inconclusive`. An inconclusive run has a `reason` for it (`null`, or left out, when completed):
  - `can_arm` and `mission_starts`, the two `assumed` preconditions;
  - `no_connection`, `upload_failed`, `no_takeoff` and `timeout` from the flyer;
  - `sim_died`, `sim_setup`, `several_logs` and `no_log` from the harness.
- **`source`:** `simulator`, `synthetic`, or what a copied run was made from.
- **`log`:** the `.ulg` file's name, or `null`.
- **`recording`:** the harness's Gazebo pose recording (`gz_pose.jsonl`). A harness that records always writes this key. If the named file is missing, empty or shorter than the log, the run is INCONCLUSIVE. Only a run flown before the harness recorded, like R02, has no `recording` key; it is read from the log alone.
- **`record`:** an object with what the run was flown with. For a simulator run, `record.px4_commit`, `record.simulator` and `record.speed` are required, because they say which tolerances apply (ADR 0005). Model, parameters and seed are optional. `recording` is a file name in the run folder.

**`readings.json`**
- **Copied from `run.json`:** `mission_id`, `run_id`, `run_status`, and `reason` when the run has one.
- **Flight setup:** Copy `record.px4_commit`, `record.simulator` and `record.speed` from `run.json` into a `record` object. Keep the values as recorded. If a field is missing, leave it out. Omit `record` when none of the three are available, as in the synthetic R01 fixture. The verifier can use these fields to identify which setup flew the mission (ADR 0005).
- **The readings:**
  - `position` and `velocity`: lists of `{t_s, x, y, z}`;
  - `landed`, `nav_state`, `disarm_reason` and `arming_state`: lists of `{t_s, value}`, with `landed` a boolean and the others integers;
  - `camera_triggered_at`: a list of `{t_s}`;
  - `camera_trigger_mode`: one value, the `TRIG_MODE` the log records (0 off, 1 on).
- **Rounding:** times to 3 decimals, positions and velocities to 4.
- **Time origin:** times are seconds from the earliest sample of `time_zero_topics` in the log. `time_zero_us` is that sample's PX4 timestamp, in microseconds, so the log's own clock can be recovered.
- **Written by the log reader:**
  - `sources`: the string `"log only"` for a run read from the log alone, or an object with one entry per reading naming its source (`gz_pose` or `log`). A schema has to allow both;
  - `missing_topics`: log topics a reading needed but the log lacks. Those readings are empty lists;
  - `cross_check`, for a recorded run: `{recording, compared, unmatched, over_limit, max_difference_m, publishers, verdict, reason}`.

  R01, made up by hand, has none of these keys, and no `time_zero_us` (it has no log). R01 and R02 are both log-only runs, so their velocity and `landed` stand for the log's own values: PX4's ground-truth velocity and land detector, not `rate_of` and the position rule.

**`gz_pose.jsonl`** (the harness's Gazebo recording, named in `run.json`'s `recording`): one JSON object per line, as `docs/px4-mappings.md` section 1 describes.
- **Pose:** `{"k": "pose", "t": <sim seconds>, "p": [east, north, up]}` for the vehicle model.
- **Publishers:** `{"k": "pubs", "pubs": [[address, type], ...]}` lists the pose topic's publishers.
- **Recorder notes:** `{"k": "info", ...}`, including any `error`.
- **Clock:** `t` × 10⁶ is the log's timestamp, with no offset.

**`expected-verdict.json`** (and the verifier's `verdict.json`)
- **Top level:** `mission_id`, `run_id`, and `verdict` (PASS, FAIL or INCONCLUSIVE).
- **`checks`:** one per check, in this order:
  1. `visited` for each goal waypoint, and `clicked_pic` for each that lists it;
  2. `goal_check`;
  3. the mission's postconditions, in their order (`hold_at`, `visits_in_order`, `stays_in_geofence`);
  4. `disarmed_after_landing`;
  5. `evidence_cross_check`, for a recorded run.
- **Each check has** `check`, `verdict` and a one-sentence `reason`. `waypoint`, `expected_s` and `observed_s` (2 decimals) appear where they apply.

## Cases to add when the verifier exists

- **A position reading before the first `nav_state`:** a stretch can't start there. Neither run exercises this (both have a mode reading first).

- **R02 cut at 45 s:** the drone is still in the air, about 56 m from the goal. Expected: INCONCLUSIVE overall, with `goal_check` and `disarmed_after_landing` INCONCLUSIVE, `hold_at` PASS (its 5.03 s stretch is already complete) and `visited` PASS. A cut-short flight is never FAIL for being cut short.
- **A hold across a log gap:** the last position reading inside the zone is at 4.72 s into the stretch, and the next reading, 0.23 s later (more than `log_gap_max_s`), is outside. The stretch ends at 4.72 s, so a 5 s hold (pass mark 4.75 s) is not met. Because the gap could hide the drone leaving, the result is INCONCLUSIVE, not FAIL.

## How the verdicts were worked out

- **Hold** (`hold_at` in `platform_configs/px4.yaml`): the longest stretch inside the zone while PX4 is in mission mode, from the first such reading to the first later reading that is outside the zone or not in mission mode. It may be up to `hold_short_by_s` (0.25 s) short of the mission's 5 s.
  - **R01:** enters at 12.00 s. PX4 switches to the return at 14.55 s, while the drone is still in the zone (it leaves at 15.40 s): 2.55 s, FAIL. Counting the return, as the old rule did, gives 3.40 s, still FAIL; a verifier that ignores the flight mode gets 3.40 s and so the wrong `observed_s`.
  - **R02:** enters at 37.184 s. PX4 leaves mission mode at 42.152 s, and the first reading after that is at 42.216 s: 5.03 s, PASS. The time the return took to climb out of the zone no longer counts: under the old rule R02 read 6.11 s. An earlier note here gave 4.97 s, measured to the switch time instead of the first reading after it.
- **`disarmed_after_landing`** (every mission gets it): the last change of `arming_state` from armed to disarmed comes at or after touchdown with reason 6, none comes between takeoff and touchdown, and the log ends disarmed. Touchdown is the first landed reading after the last airborne one.
  - **R01:** armed at 0.40 s, touchdown at 24.00 s, disarmed with reason 6 at 26.00 s, the end of the log. PASS. The 2.00 s is made up: in real flights PX4 disarms about 3 s after a touchdown worked out from position, which is 2 s (`COM_DISARM_LAND`) after its own land detector.
  - **R02:** armed once, touchdown at 85.376 s, disarmed with reason 6 at 87.392 s, and still disarmed at the end. PASS.
- **`goal_check`:** the last readings match the goal state: within 0.5 m of the base, landed, and slower than 0.1 m/s.
- **`visited`:** any reading inside the zone.

The expected values were worked out from the readings by hand, not taken from a verifier.

## Where the runs came from

- **R01:** written by hand. No simulator and no log. One sample every 0.05 s. Its flight mode, arming state and disarm reason are made up too, as PX4 would publish them on a change: mission mode (3) from 0.5 s, return (5) from 14.55 s, as the drone starts back while still at W1, armed from 0.40 s, and the disarm (reason 6) at 26.00 s, 2 s after touchdown.
- **R02:** one of my local Gazebo runs, not a shared team run.
  - PX4 build `fca3df865a` (the build the repo pins, ADR 0001), SITL with Gazebo, model `gz_x500`, sim speed 4x
  - Plan flown: `mission.plan` in this folder
  - Readings: every sample of `vehicle_local_position_groundtruth` (position and velocity), `vehicle_land_detected` (landed) and `vehicle_status` (`nav_state`, `arming_state` and `latest_disarming_reason`), read with `log_only_readings` in `platform_configs/px4.yaml`. R02 was flown before the harness recorded Gazebo's pose, so it is read from the log alone, and its `landed` is PX4's land detector. Nothing was trimmed. Times are seconds from the earliest sample of those two topics. Positions and velocities are rounded to four decimals.
  - Log: `R02.ulg`, md5 `6e43a1b089e2b3d364321ccc2b04480c`. It is only on my machine for now. Checking a verifier against these readings works today; re-reading the log is not something a teammate can repeat yet.

