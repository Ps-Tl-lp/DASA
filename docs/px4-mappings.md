# PX4 mappings: the detail behind `platform_configs/px4.yaml`

Nov 20, 2026, updated Nov 23. The blank "Team check" cells are for our row-by-row review.

**First time through:** read the tables. The bullets under them and all of section 5 are backup (caveats and exact numbers from the two logs). Come back to them when a row raises a question.

**The two logs** are simple-mission flights from my local runs: `simple_gz_1.ulg` (Gazebo) and `simple_sih_1.ulg` (SIH, the simulator built into PX4). The mission is: take off to 20 m, fly 50 m north to W1, hold 5 s, return home and land.

Both logs were flown on PX4 build `fca3df865a`, the build the repo pins (ADR 0001). Doc links go to the latest PX4 docs, which can change. Three links go to that build's source code, for behaviour the docs do not describe.

## 1. State properties from the log

**Since the config decisions of 2026-11-23,** position, velocity and `landed` come from the harness's recording of Gazebo's `/world/default/pose/info`, not from the log. That is the same data PX4 logs as `vehicle_local_position_groundtruth`: sample for sample, within 2.1 µm, in a local spike. The log's copy is checked against the recording (`cross_check` in `px4.yaml`), and a run whose log disagrees is INCONCLUSIVE. Velocity is the change in position between readings, and `landed` is worked out from position (on the ground and still). The tables below give the log's side, which a run with no recording still uses.

For a goal requirement, compare the readings with the required value: PASS or FAIL when they decide it, INCONCLUSIVE when it is missing or invalid. The final sample stands for the goal in these two logs because each holds one complete flight. If a log ends early or carries on into something else, its last sample does not show the mission's final state.

| Property | Log topic and field | Calculation | Why this field | Gazebo log | SIH log | Team check |
|---|---|---|---|---|---|---|
| `agent.x` | `vehicle_local_position_groundtruth.x` | value − first value | North position in metres. Ground truth is the simulator's own position, not PX4's estimate. | −0.08 | 0.26 | |
| `agent.y` | same topic, `y` | value − first value | East position in metres. | −0.02 | 0.09 | |
| `agent.z` | same topic, `z` | −(value − first value) | PX4's `z` is down, ours is up. | 0.00 | 0.00 | |
| `agent.velocity.x` | same topic, `vx` | value | North speed, m/s. | 0.00 | 0.00 | |
| `agent.velocity.y` | same topic, `vy` | value | East speed, m/s. | 0.00 | 0.00 | |
| `agent.velocity.z` | same topic, `vz` | −value | PX4's `vz` is down, ours is up. | 0.00 | 0.00 | |
| `agent.landed` | `vehicle_land_detected.landed` | last value | PX4's land detector: true once it judges the vehicle is on the ground. | true | true | |
| `waypoint.visited` | none: worked out from the path | at the waypoint (`tolerances.at_waypoint`) at any point in the flight | The same zone the plan and the hold check use. A mission may still require takeoff, visit order or a continuous hold. | see section 5 | see section 5 | |

Docs: [VehicleLocalPosition](https://docs.px4.io/main/en/msg_docs/VehicleLocalPosition.html) (fields, units, and the list of topics that use it, including the ground-truth one), [VehicleLandDetected](https://docs.px4.io/main/en/msg_docs/VehicleLandDetected.html).

- **Why subtract the first value.** The simulator's origin need not be our (0, 0, 0). In both logs the first value is within 0.02 m of zero, so the subtraction is a safeguard. It does mean the mapping assumes the drone starts at home. A log that starts after liftoff, or a vehicle that starts elsewhere, needs a separately known home reference. In a local spike of mine, 3 of 10 SIH flights at 10x speed logged from mid-air (first position 2.6 to 5.2 m up); none of 5 Gazebo flights did. The first `landed` sample is false in exactly those logs, which would make a cheap check. It is not in `px4.yaml`, because the demo flies Gazebo.
- **A start-state check on position would always pass,** because the first position is (0, 0, 0) by construction. Checking the start state against the log needs a different source for position.
- **Ground truth comes from the simulator.** A real vehicle lacks this simulator topic. PX4's estimated position is a different source of evidence.
- **`landed` is now the simulator's, the disarm check is still PX4's own report.** `landed` is worked out from the recorded position: within `tolerances.landed.height_m` (0.1 m) of the start height and slower than `tolerances.landed.speed_m_s` (0.1 m/s). In 28 Gazebo flights the drone was within 0.001 m and 0.001 m/s while PX4 said landed. Touchdown that way comes 0.95 to 1.10 s before PX4's land detector says landed, and lift-off 2.70 to 2.82 s after PX4 says "not landed" (PX4 flips at arming, before the drone leaves the ground).
- **A vehicle can be landed without ever flying.** In a never-armed log I had locally (`unkown_mission.ulg`, not a team file), `landed` stays true. If takeoff is required, check that the vehicle left the ground during this run.
- **Time** in the log is the message `timestamp` divided by 1,000,000: seconds since PX4 started. Readings count from the earliest sample of `time_zero_topics` instead, and carry that sample's timestamp as `time_zero_us` (`tests/fixtures/m01/README.md`, File formats).

**How the readings are made** (moved from `px4.yaml`'s comments on `readings` and `cross_check`):

- **Sources.** Position, velocity and `landed` come from the recording, so a PX4 that changes its log can't change them. There is one position reading per recorded sample. The flight mode, arming state, disarm reason and camera trigger are PX4's own reports, from the log.
- **`subtract_first`** subtracts the first value inside the readings' span: the recording's sample at the log's first ground-truth sample. Positions are then measured from the base, where the drone sat before takeoff, instead of from the simulator's origin.
- **Time and span.** Reading times are seconds from the earliest sample of `time_zero_topics` in the log, leaving out a topic the log lacks. The readings cover the log's own span, its first to last ground-truth sample, so a log cut short gives readings cut short.
- **The log-only path** (`log_only_readings`) keeps every sample its topics logged. It isn't cut to the ground-truth span.
- **The recording** (`run.json`'s `recording`, a file name in the run folder) is JSON lines written by the harness:
  - a pose line is `{"k": "pose", "t": sim seconds, "p": [east, north, up]}` for the vehicle, which is the first model on `sim.pose_topic` whose name starts with `sim.vehicle_model_prefix`;
  - a `{"k": "pubs"}` line lists the topic's publishers;
  - a `{"k": "info"}` line carries the topic, the model found, or an `error`.
- **Coverage and clock.** The harness starts the recorder before PX4 starts logging, so the recording covers every log sample. At 4x its samples are 0.068 s apart, like the log's. In SITL lockstep PX4's clock is the sim clock, so `t` × 10⁶ is a log timestamp with no offset (2026-11-23 spike). A recorded sample's reading time is (`t` × 10⁶ − `time_zero_us`) / 10⁶ seconds.
- **The cross-check.**
  - **Why it works.** PX4's `gz_bridge` reads the same Gazebo topic, so in a correct run every log sample has a recorded sample at the same sim time with the same position. A Gazebo spike on 2026-11-23 matched 1403 of 1403 samples within 2.1 µm, and 5 flights with a full recording matched within 5.2 µm. PX4 logs the ground truth as float32, which rounds it by that much. Both clocks sit on Gazebo's 4 ms physics step, and in those 5 flights every log sample had a recorded one at the same stamp.
  - **How it compares.** Positions are compared in the world frame, before `subtract_first`. Down is the log's `z`, compared with the recording's up flipped.
  - **Outcomes.** A harness that records always names the recording in `run.json`, even if the recorder failed. A run that names a recording whose file is missing, empty or shorter than the log is INCONCLUSIVE. Only a run with no `recording` key at all, flown before the harness recorded, has no cross-check: it is read from the log alone and judged on it.
  - **A disagreement** makes the run INCONCLUSIVE, whatever the other checks say, and is reported as its own check, `evidence_cross_check`. A log that doesn't match the simulator is invalid evidence, and a variant that edits its own log is a finding in itself.

### Declarations and mappings

| Property | Mapping | On the two logs | Doc |
|---|---|---|---|
| `agent.has_camera`, `agent.has_grippers` | Not read from the log. The start state gives the vehicle type, and the vehicle type sets them. | Nothing shows what is fitted. `PD_GRIPPER_TYPE` reads 0 ("Binary Grab/Release") with no gripper on the vehicle, so it cannot confirm one. | [Gripper](https://docs.px4.io/main/en/peripherals/gripper.html) |
| `waypoint.clicked_pic` | A `camera_capture` entry whose time falls while the agent is at the waypoint. Look the agent's position up at that time: the latest position reading at or before it. | No capture topic in either simple log (`TRIG_MODE` 0, no camera item). One capture in each spike flight with `TRIG_MODE` 1. | [CameraCapture](https://docs.px4.io/main/en/msg_docs/CameraCapture.html) |

A gripper command can occur without a gripper. Both logs also have a camera trigger-control command (2003) at mission end on vehicles without a camera. The docs say `camera_capture.result` is -1 when the camera gives no feedback. The spike logs show 1 with no camera fitted, so the log proves PX4 triggered the camera, not that an image exists. With `TRIG_MODE` at 1, no capture means the picture was not triggered. With `TRIG_MODE` at 0 the trigger is off: a 203 flown that way logged the command and no capture. On a camera vehicle type, a log whose `TRIG_MODE` is not 1 means the trigger was off and the outcome is unknown. A type with no camera flies with the trigger off, so `clicked_pic` stays false there. [PX4 camera feedback source](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/src/modules/camera_feedback/CameraFeedback.cpp#L92-L154)

`agent.is_carrying` and `agent.was_attacked` were removed on Nov 21. If either comes back: a gripper command or a failure-injection request (`vehicle_command` 420) records a request only, not that anything happened, and the gripper codes differ by source (a grab is 1 in MAVLink command 211 and 0 in the PX4 `gripper` topic).

## 2. Evidence for postconditions

These are not state properties. They are what the verifier reads to check a postcondition.

| Postcondition | Log topic and field | Calculation | Gazebo log | SIH log | Team check |
|---|---|---|---|---|---|
| Disarms after landing | `vehicle_status.arming_state` and `latest_disarming_reason`, and `landed` | the last change from armed to disarmed comes at or after touchdown with reason 6, none comes between takeoff and touchdown, and the log ends disarmed. Every mission gets this check | 6 | 6 | |
| Stays inside the geofence | none: worked out from the path | any reading further from the base than the mission's geofence distance, or higher than its height, fails | this mission has no geofence | this mission has no geofence | |
| Visits in order | none: worked out from the path | walk the waypoints in the required order; each needs a time at it after the time matched for the one before | one waypoint, nothing to order | one waypoint, nothing to order | |
| Holds at each waypoint | the path, and `vehicle_status.nav_state` | longest stretch at the waypoint (`tolerances.at_waypoint`) while PX4 is in mission mode (`nav_state` 3), at least the hold minus `tolerances.hold_short_by_s`. A log gap longer than `tolerances.log_gap_max_s` ends a stretch (section 5) | see section 5 | see section 5 | |
| No collision or crash (proposed) | four sources, see below | four warning signs, not enough to clear a flight | no signs | no signs | |
| Time limit (proposed) | `vehicle_status.arming_state` | time from arming to disarming | 78.0 s | 85.6 s | |
| Battery limit (proposed) | `battery_status.remaining` | lowest value while armed (0 to 1) | 0.50 | 0.50 | |

Docs: [VehicleStatus](https://docs.px4.io/main/en/msg_docs/VehicleStatus.html), [BatteryStatus](https://docs.px4.io/main/en/msg_docs/BatteryStatus.html).

- **Disarming.** Reason 6 means PX4 disarmed itself after detecting a landing. That numbering is from the pinned build and matches the current docs. PX4 v1.13 to v1.16 used 7 for it, and 6 meant the safety button. In both flights `landed` turns true about two seconds before the disarm (97.02 s then 99.03 s in Gazebo, 90.28 s then 92.30 s in SIH). Two limits: a disarm sent by command has a different reason, and the last reason alone does not show whether the vehicle armed again. If either matters, check the order of events instead: left the ground, landed, then armed to disarmed. **The check (decided):** it reads `arming_state` as well, because PX4 keeps the last disarm reason while it is armed: the reason alone can't show a re-arm, or a second disarm with the same reason. The last change from armed to disarmed has to come at or after touchdown with reason 6, none may come between takeoff and touchdown, and the log has to end disarmed. That handles both limits, and a 6 left over from before takeoff, and it makes a log that stops between touchdown and the disarm INCONCLUSIVE. A disarm after touchdown with another reason is FAIL. In 28 later Gazebo flights the change came 2.96 to 3.12 s after touchdown worked out from position (call 3), and 2.008 to 2.016 s after PX4's own land detector said landed, which is `COM_DISARM_LAND` (2 s by default).
- **Collision or crash.** The four signs are the disarm reason, failure-detector flags, freefall, and final ground-truth tilt. In a separate local test run of mine (`contact2_1`), Gazebo recorded a rotor touching a box at 34.9 s. That flight's log still shows a landing disarm, clear flags, no freefall and 0° final tilt. So the four signs cannot clear a flight of a collision. The simulator's own contact record can show one. The two demo flights ended at 0.0° and 2.7°. The pinned build has `fd_roll` and `fd_pitch`. The [current message](https://docs.px4.io/main/en/msg_docs/FailureDetectorStatus.html) lists `fd_tilt`.
- **Battery: read the lowest value, not the last.** PX4 reserves −1 for an invalid fraction. Missing coverage cannot clear a battery limit. The reported fraction recovers after disarming, to 0.80 and 0.78 by the end of the logs. See also the 50% floor in section 3.
- **Time and battery limits are not demo postconditions.** The mappings are here because they were cheap to check. The limits themselves would be written with the postconditions.
- **The required hold comes from the mission settings.** In M01, `hold_at_each_waypoint: {min_s: 5}` asks for five seconds at every waypoint. The plan step reads it to write `goto`'s hold. The verifier checks against the mission's number, not the plan's (5 s for the simple mission).

### Outcomes of each check

Moved from `px4.yaml`'s comments. Each check gives PASS, FAIL, or INCONCLUSIVE when the log can't settle it. Which postconditions a mission has, and their values (the geofence size, the hold at each waypoint, the order), come from the mission.

- **How checks combine.** A run's verdict is INCONCLUSIVE if the log doesn't match Gazebo's recording (`cross_check`). Otherwise it is FAIL if any check is FAIL, else INCONCLUSIVE if any is INCONCLUSIVE, else PASS.
  - **Every check reports.** Every check runs and reports, whatever the others give, so the report lists every problem. A run the harness marks inconclusive (an `assumed` precondition failed, or the flight didn't finish) still lists every check, each INCONCLUSIVE with the harness's reason.
  - **The cross-check** comes from `readings.json`'s `cross_check`, and the verifier reports it as one more check, `evidence_cross_check`.
- **FAIL only on evidence.** A check is FAIL only on a violation seen in the log. One the log stopped too early to settle is INCONCLUSIVE, so a flight cut short in the air is never FAIL for being cut short. Two more cases where the evidence can't settle a check:
  - **A gap.** The position readings may have a gap longer than `tolerances.log_gap_max_s`. Then a check that would FAIL or PASS because something didn't happen (no visit, hold or order step, or no reading outside the geofence) is INCONCLUSIVE, since the gap could hide it. A check that FAILs on something that did happen (a reading outside the geofence, a disarm in the air) stays FAIL.
  - **Missing.** A check whose reading is empty, or whose topic is in `missing_topics`, is INCONCLUSIVE. `camera_triggered_at` is the exception: its topic is absent when nothing triggered, so an absent topic with `camera_trigger_mode` 1 means no picture.
- **`derived` (`visited`, `clicked_pic`).**
  - **PASS** when the readings agree with the goal's value.
  - **FAIL** when they don't and the log ends on the ground. FAIL at once when the goal wants false and the readings show true, wherever the log ends.
  - **INCONCLUSIVE** when the goal wants true, the readings don't show it yet and the log ends in the air, because it could still happen.
  - **Already true at the start.** A property already true in the start state needs no task: PASS if the goal keeps it, FAIL if it doesn't.
  - **`clicked_pic`.** A goal waypoint that doesn't list `clicked_pic` gets no `clicked_pic` check. A trigger counts at the waypoint if the latest position reading at or before it is inside the zone. If the goal wants a picture but `camera_trigger_mode` is 0 (the trigger was off), the result is INCONCLUSIVE, because no capture could have been recorded.
- **`goal_check`.** Each log holds one flight, so the last reading is the end of the flight. For a log cut off before the disarm, `disarmed_after_landing` is INCONCLUSIVE. PASS when every comparison holds at the last reading. FAIL when one doesn't. INCONCLUSIVE when the log ends in the air: the end of the flight isn't in the log.
- **`stays_in_geofence`.** FAIL at the first reading outside. PASS if none is outside and the log ends on the ground. INCONCLUSIVE if none is outside so far but the log ends in the air. A mission with no geofence passes.
- **`hold_at`.** There is one check per waypoint the mission wants a hold at.
  - **Mission mode only.** Time counts only while PX4 is flying the mission, so the time the drone takes to leave the zone after switching to the return doesn't count (section 5).
  - **Stretches** are made of position readings. A stretch's length is the time between the reading that starts it and the reading that ends it.
  - **No mode yet.** A position reading before the first `nav_state` can't start a stretch, and a log with no `nav_state` gives INCONCLUSIVE.
  - **PASS** if one stretch lasts at least the mission's hold minus `short_by_at_most`.
  - **FAIL** if none does, the log ends on the ground, and the position readings have no gap longer than `max_gap`.
  - **INCONCLUSIVE** if none does and the log ends in the air or has such a gap, or if the log stops while the drone is still there and the hold isn't complete.
  - **Gaps.** A gap longer than `max_gap` between consecutive position readings ends a stretch at the last position reading before the gap, so no time is credited across it. Gaps in `nav_state` don't count: PX4 publishes it about every 0.5 s and on each change. After a gap, the next position reading inside the zone in mission mode can start a new stretch. A stretch that already proves the hold still passes. A stretch still open when the log stops ends at its last position reading.
- **`visits_in_order`.** PASS if every waypoint gets a time. FAIL if one doesn't and the log ends on the ground; INCONCLUSIVE if it ends in the air.
- **`disarmed_after_landing`.** It is what makes a log a complete flight. It is also what makes a log that stops after touchdown but before the disarm INCONCLUSIVE (R5), so every mission gets it. PX4 writes `arming_state` and the disarm reason in the same message. It keeps the last disarm reason while it is armed ([Commander.cpp at fca3df865a](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/src/modules/commander/Commander.cpp)), so the reason alone can't show a re-arm or a second disarm.

  | Outcome | When |
  |---|---|
  | PASS | the last disarm is at or after touchdown with reason `last_value`, there is no disarm between takeoff and touchdown, and the log ends disarmed |
  | FAIL | a disarm between takeoff and touchdown (in the air), or a last disarm after touchdown with another reason (something other than PX4's landing disarm) |
  | INCONCLUSIVE | no disarm at or after touchdown (the log stops first), or the log shows no takeoff and touchdown (the other checks report that flight) |

## 3. Preconditions: what the numbers depend on

The flight area, each mission's geofence, the waypoint height and the "at the waypoint" zone are our numbers, not PX4's. These PX4 parameters set what they have to respect. Values are from the saved ULogs.

A mission the drone can't complete tells us nothing about a variant, so the generator only outputs missions that pass every precondition. A mission setting (simple, medium, survey) outside the global ranges is an error when it loads. The flight area is our own limit, since PX4 and Gazebo don't set one. A mission with no geofence can put its points anywhere in the flight area.

**Why `px4_setup` lists values PX4 already uses.** On the pinned build every value in `px4_setup` is what PX4 already uses for a multicopter. Listing them changes nothing today, but it pins them against a PX4 change and gives the preconditions a value to read. All but `RTL_RETURN_ALT` are PX4's documented defaults (see below). Of the settings in the config, only `multicopter_camera`'s `TRIG_MODE` changes what PX4 does. `NAV_MC_ALT_RAD` would too, if `at_waypoint.height_within_m` moved off 0.8.

| Parameter | In both logs | What it does | What it means for our numbers |
|---|---|---|---|
| [RTL_RETURN_ALT](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_RETURN_ALT) | 30 m | PX4 climbs to this before flying home | A mission's geofence must be this tall plus `tolerances.geofence_clearance_m`, or correct flights break it on the way home (the `stays_in_geofence` precondition). Both flights went over it: 30.05 m and 31.08 m |
| [NAV_ACC_RAD](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#NAV_ACC_RAD) | 10 m | How close PX4 has to get before it counts a waypoint reached | Used only when `goto`'s acceptance radius is 0. Ours is `at_waypoint.within_m`, so waypoint spacing depends on that instead: more than twice it |
| [MIS_TAKEOFF_ALT](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MIS_TAKEOFF_ALT) | 2.5 m | Takeoff height (see the caveat below) | Not the basis for `waypoint.z`'s 5 m minimum, which is the lowest height we test. The lowest waypoint flown so far is 6 m, in one older local flight of mine. 5 m itself has not been flown |
| [GF_MAX_HOR_DIST](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#GF_MAX_HOR_DIST), [GF_MAX_VER_DIST](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#GF_MAX_VER_DIST) | 0 (off) | PX4's own geofence, a cylinder around home | Off (`px4_setup`). The verifier checks each mission's geofence from the log instead |

- **`RTL_RETURN_ALT` is 30 m here, 60 m in the docs.** PX4's multicopter defaults set 30 on the pinned build ([source](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/ROMFS/px4fmu_common/init.d/rc.mc_defaults)). The docs list 60 m as the general default ([Return mode](https://docs.px4.io/main/en/flight_modes_mc/return.html)). The generator needs the value the flight will actually use, so `px4_setup` sets it to 30 and the `stays_in_geofence` precondition reads it from there.
- **Flight area: 200 m out, 50 m up (decided).** Our `survey.plan` reaches 170 m from the base and flies at 30 m. A geofence has to be at least 32 m tall (the 30 m return climb plus the 2 m clearance), and a waypoint at 30 m needs the same, so 50 m leaves room. It leaves room for waypoints up to 48 m. At 200 m the plan's sphere and Gazebo's WGS84 differ by at most about 0.6 m east-west (section 5), inside `at_waypoint.within_m`.
- **Why PX4's geofence stays off.** With it on, PX4 takes over when the drone crosses it (hold or return, depending on `GF_ACTION`). That can hide a variant that drifts, which is what we are testing for. With it off, the drift shows in the log and the `stays_in_geofence` postcondition fails the run. The flight area is how far out the generator may place a mission; each mission's geofence sits inside it and comes from the mission's settings. See [Safety: geofence](https://docs.px4.io/main/en/config/safety.html).
- **PX4 already blocks some missions itself.** It will not start a mission whose items conflict with a geofence, or one missing a takeoff or landing item when `MIS_TKO_LAND_REQ` asks for them. A first waypoint further than `MIS_DIST_1WP` from home only gets a warning. See [Mission mode: feasibility checks](https://docs.px4.io/main/en/flight_modes_mc/mission.html). Our generator could lean on this or copy it. Not decided.
- **A log does not record every parameter.** `MIS_TKO_LAND_REQ` and `MIS_DIST_1WP` are in the SIH log and absent from the Gazebo log. A setting the log does not record cannot be confirmed from it.
- **Speed limits are not in the config.** A start state and a goal state are both at rest, so a speed range has nothing to limit yet. If one is needed later, note that [MPC_XY_VEL_MAX](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MPC_XY_VEL_MAX) (12 m/s in both logs) is a configured limit on commanded horizontal speed. Mission cruise speed comes from [MPC_XY_CRUISE](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MPC_XY_CRUISE) (5 m/s in both logs, and the fastest flown was 5.06 m/s). A measured speed can also pass its parameter: [MPC_Z_VEL_MAX_DN](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MPC_Z_VEL_MAX_DN) is 1.5 m/s and the SIH flight descended at 1.70 m/s.
- **`MIS_TAKEOFF_ALT` (2.5 m in both logs) is not the basis for the 5 m minimum.** The mission-mode page calls it the minimum takeoff altitude, the parameter reference calls it the default, and no flight of ours has tested which. At the 5 m minimum, a waypoint's zone reaches down to 4.2 m. Check before using it as a lower bound on takeoff height.

Can arm, enough battery and a path exists:

- **Can arm: `assumed`, not checked.** PX4 reports it at the start of a run (`vehicle_status.pre_flight_checks_pass`, 1 in both logs). Nothing in a generated mission's values decides it. If arming fails, the harness marks the run INCONCLUSIVE, so a flaky run is not counted against a variant. The harness passes the reason on with the run, so the verifier doesn't judge the log as a normal flight. `mission_starts` is the same idea: in a local trial of mine, 1 of 17 flights armed, PX4 refused the switch to Mission, and the runner disarmed it. That log never leaves the ground and ends with disarm reason 4 (external command). Checked as a normal flight it would read FAIL.
- **Enough battery for the trip: not checked.** The simulated battery stops draining at 50% by default ([Simulate failsafes](https://docs.px4.io/main/en/simulation/failsafes.html)), and the measured minimum rounds to 0.50 on both flights, so a battery condition can't fail in the default simulator. A route-length limit was considered and cut: the geofence and the waypoint count already cap the route.
- **A path exists: no rule needed for the demo.** With no-fly zones dropped, the only area rule is the flight area, a cylinder. A straight leg between two points inside it stays inside it. PX4 can round turns and climbs on return ([Mission mode](https://docs.px4.io/main/en/flight_modes_mc/mission.html)), which is why a mission's geofence has to clear `RTL_RETURN_ALT` with some room. If no-fly zones or obstacles come back, this needs a real check.
- **Equipment: checked through the tasks, not by its own rule.** The vehicle type sets `has_camera` and `has_grippers`, and a task's `needs` says what equipment it requires. `every_change_has_a_task` runs the plan step on the drawn mission, so a mission that needs equipment the drone doesn't have has no plan and is rejected. The harness launches the type's `sim_model`, so the state always matches the drone that actually flies.

## 4. Tasks to plan items

### How the plan step is meant to use `tasks`

Agreed on Nov 21, changed on Nov 23. A task's `sets` is the change it makes, and its `needs` is what has to be true first. The plan step builds the task list in a fixed order (takeoff, the gotos, each picture straight after its goto, return home), then walks it from the start state: each task's `needs` must hold, its `sets` apply, and the result must equal the goal state. If any step fails there is no plan, and the reason names the task and the property. Our missions have one way to reach their goal, so a real planner (a search over `needs` and `sets`) waits until one has more. The example below is why the fixed order passes the check.

The simple mission as an example. The start and goal states differ in one property: `waypoint.W1.visited` goes from false to true.

1. `goto` sets `visited` to true. It needs `agent.landed` to be false, so `takeoff` goes first.
2. After `goto` the agent is at W1 and in the air. The goal state has it at its base and landed, so `return_home` goes last.

Result: `takeoff`, `goto W1`, `return_home`. Those are the three items in our `simple.plan`.

**The plan step's rules in full** (moved from `px4.yaml`'s comment on `tasks`):

- **The fixed order.**
  - First, takeoff.
  - Then a `goto` for each waypoint whose `visited` or `clicked_pic` changes, or that a `hold_at` or `visits_in_order` postcondition names. The waypoints in `visits_in_order` come first, in that order, then the rest in waypoint id order.
  - Each `take_picture` comes straight after its waypoint's `goto`.
  - Last, `return_home`.
- **No change, no task.** A property that didn't change gets no task. If a waypoint's `clicked_pic` is false in both states there is no `take_picture`, even though the waypoint exists. If no property changes and no `hold_at` names a waypoint, the plan has no items at all, not even a takeoff. A waypoint a `hold_at` names still gets its goto, as the fixed order says, even if it was already visited at the start.
- **The check.** Walk the list from the start state: each task's `needs` must hold, then its `sets` apply. The result must equal the goal state on every property the goal lists. Positions compare exactly, because they are the mission's numbers, not flown ones.
- **When there is no plan.** Any failure means no plan, and the reason names the task and the property. The same goes for a `hold_at` or `visits_in_order` that names a waypoint the mission doesn't have, or one the goal says isn't visited.
- **What the check can't see.** The states can't show order or time, so neither can the check. The order comes from the fixed order above, and the verifier checks order and holds after the flight.

- **Why compare the states instead of just visiting every waypoint.** For our current missions both give the same plan. The difference shows up with anything else: a waypoint with `clicked_pic` false in both states gets a `goto` (its `visited` changed) but no `take_picture`. One rule covers every task.
- **The difference alone isn't enough.** Takeoff and return leave no net change between start and goal. They come from `needs` and from where the goal state puts the agent.
- Takeoff height is the height of the first waypoint the plan flies to (`$height` in `inputs`). Our three plans already do that (20, 20 and 30 m). Hold time (`$hold_s`) and waypoint order come from the mission's postconditions, which the plan step reads from the settings file alongside the two states. With no order asked for, it uses waypoint id order.

The medium mission adds an order requirement. Its fourth waypoint has the same coordinates and altitude as the takeoff item. Checking each waypoint's first visit could put W4 first on a correct run. Look for a qualifying W4 visit after W3. Flown in a local spike of mine (three flights, 2 m radius): "a visit to each waypoint after the previous one's visit" passed two correct flights and failed one flown in the wrong order. First-visit order failed the two correct flights.

**Why `waypoint_spacing`.** A visit or hold at one waypoint must not count for another. Two zones are apart when their centres are more than twice `within_m` apart sideways, or more than twice `height_within_m` apart in height.

One gap: a waypoint straight above the base reads as visited on any flight, because takeoff and the return's descent pass through its zone. Two simple-mission flights "visited" a point at (0, 0, 20) that was never in their plan. So `waypoint_spacing` keeps every waypoint more than twice `within_m` sideways from the base, whatever its height. Our `medium.plan` ends on a waypoint over the base, so a generated mission won't have that one; `return_home` makes the trip back. The order rule is `visits_in_order` in `px4.yaml`.

More generally, any leg that crosses another waypoint's zone counts as a visit to it, and so would the return leg at `RTL_RETURN_ALT`. Not handled. Order and hold are also checked separately: "visit A, then hold at B" would pass on a flight that held at B first and only crossed B again after A. No current mission asks for both, so this is not handled either.

The survey plan has 12 waypoint items defining its lawnmower route. On the sample survey trace in `ulog-extract-demo`, flown with PX4's default radius, the drone came inside the 2 m zone of one waypoint out of twelve. Flown twice with the 2 m radius in the plan (Gazebo at 4x, local runs of mine), it entered all twelve zones in plan order and passed at most 1.20 m from each waypoint. So `visited` works for survey once its plan carries the new radius.

No task here lands away from home. `return_home` is the only task that sets `agent.landed` to true. Landing elsewhere would need a land task (MAVLink command 21).

### The plan items

`command` and `frame` are numbers from MAVLink, the message format PX4 and ground stations share. `params` is the seven-slot list each `.plan` item carries.

| Task | Command | Frame | What the params carry | Team check |
|---|---|---|---|---|
| `takeoff` | 22, [MAV_CMD_NAV_TAKEOFF](https://mavlink.io/en/messages/common.html#MAV_CMD_NAV_TAKEOFF) | 3 | 5 and 6: latitude and longitude. 7: height. | |
| `goto` | 16, [MAV_CMD_NAV_WAYPOINT](https://mavlink.io/en/messages/common.html#MAV_CMD_NAV_WAYPOINT) | 3 | 1: hold time in seconds. 2: acceptance radius, `tolerances.at_waypoint.within_m` (2 m; at 0 PX4 uses `NAV_ACC_RAD`, see section 5). 5 to 7: latitude, longitude, height. | |
| `return_home` | 20, [MAV_CMD_NAV_RETURN_TO_LAUNCH](https://mavlink.io/en/messages/common.html#MAV_CMD_NAV_RETURN_TO_LAUNCH) | 2 | Nothing. `px4_setup` sets RTL_TYPE 0 and RTL_LAND_DELAY 0 (land on arrival). Our plans have no rally points. | |
| `take_picture` | 203, [MAV_CMD_DO_DIGICAM_CONTROL](https://mavlink.io/en/messages/common.html#MAV_CMD_DO_DIGICAM_CONTROL) | 2 | 5: 1 takes one picture. | |

- **Frame 3** means latitude and longitude with height measured from home. **Frame 2** is MAV_FRAME_MISSION. RTL has no position arguments. See [MAV_FRAME](https://mavlink.io/en/messages/common.html#MAV_FRAME).
- The three items match our own `simple.plan` item for item: same commands, frames and param layout. The one change is `goto`'s param 2, which `simple.plan` leaves at 0.
- **`take_picture` has been flown once per setup,** in a local spike of mine (Gazebo and SIH, the old acceptance radius, a 5 s hold at W1). The item as written logged one `camera_capture` when W1's hold ended. In Gazebo the drone was 0.26 m from W1 at that moment on the plain x500 and 0.29 m on `gz_x500_mono_cam`.
  - Flown again since with the 2 m radius on `gz_x500_mono_cam`: one capture, 0.04 m from W1. The same plan on the plain `gz_x500` with the trigger off logged the command and no capture. Not flown: a picture at a waypoint with no hold.
  - `take_picture` relies on `TRIG_INTERFACE`, which is 3 (MAVLink) in every SITL log so far. The docs list 4 as the general default.
  - The trigger needs `TRIG_MODE` 1, set when PX4 starts ([trigger modes](https://docs.px4.io/main/en/camera/fc_connected_camera.html)). The docs say the camera on `gz_x500_mono_cam` cannot yet be used for image capture ([Gazebo vehicles](https://docs.px4.io/main/en/sim_gazebo_gz/vehicles.html)), so nothing ties a rendered frame to PX4's trigger.
  - PX4 lists two ways to take one picture in a mission. Command 203 goes through PX4's camera trigger driver, and each trigger is logged as `camera_capture` ([Cameras connected to flight controller outputs](https://docs.px4.io/main/en/camera/fc_connected_camera.html), [camera architecture](https://docs.px4.io/main/en/camera/camera_architecture.html)). Command 2000 (MAV_CMD_IMAGE_START_CAPTURE) is documented as passed on to a MAVLink camera without PX4's trigger and feedback modules ([MAVLink cameras](https://docs.px4.io/main/en/camera/mavlink_v2_camera.html)), though the one spike flight that used 2000 logged a 203 and a capture anyway. The config uses 203 because it is the documented route into the log. The task needs the agent at the waypoint, so it goes straight after that waypoint's `goto`.
- PX4's reading of each command's params is in [VehicleCommand](https://docs.px4.io/main/en/msg_docs/VehicleCommand.html). The item keys in `plan_item_defaults` are from the [QGroundControl plan format](https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/file_formats/plan.html). That page also lists `doJumpId`, numbered from 1, and our three plans all carry it, so the plan step numbers the items the same way (`doJumpId: $index`). Our `simple.plan` uses `AltitudeMode: 1` with `Altitude` equal to param 7 (`Altitude: $item_height`). The medium plan omits both keys on RTL.
- **The hold time in the plan is a command to PX4.** The PX4 docs describe param 1 as time to stay inside the acceptance radius ([NavigatorMissionItem](https://docs.px4.io/main/en/msg_docs/NavigatorMissionItem.html), `time_inside`). The pinned build does something slightly different: it marks the waypoint reached once, then counts from that moment without checking the drone is still inside ([source](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/src/modules/navigator/mission_block.cpp#L380-L433)). Whether the drone held for five seconds by our definition is a separate question (section 5).

PX4 parameters that change what an item does. `px4_setup` sets `RTL_TYPE`, `RTL_LAND_DELAY`, `RTL_RETURN_ALT` and `NAV_MC_ALT_RAD` (all at the values below; `NAV_MC_ALT_RAD` by pointing at `tolerances.at_waypoint.height_within_m`). The rest stay at PX4's defaults:

| Parameter | In both logs | What it changes |
|---|---|---|
| [NAV_ACC_RAD](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#NAV_ACC_RAD) | 10 m | How close PX4 counts as having reached a waypoint, unless the item gives its own radius |
| [NAV_MC_ALT_RAD](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#NAV_MC_ALT_RAD) | 0.8 m | The same, for height |
| [RTL_TYPE](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_TYPE) | 0 | Where a return goes. 0 is home, or a rally point (an alternative landing spot) if one is closer. Our plans have none. |
| [RTL_RETURN_ALT](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_RETURN_ALT) | 30 m | The drone climbs to this height before flying back, unless it is already higher |
| [RTL_DESCEND_ALT](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_DESCEND_ALT) | 10 m | The height it drops to over home before landing |
| [RTL_LAND_DELAY](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_LAND_DELAY) | 0 s | The wait at that height before landing. −1 means hover and never land. |
| [RTL_MIN_DIST](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_MIN_DIST), [RTL_CONE_ANG](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_CONE_ANG) | 10 m, 45° | Close to home, the return height can be lower than `RTL_RETURN_ALT`. On the pinned build `NAV_ACC_RAD` decides it: within 10 m of home the return climbs to twice the distance. The cone is used only between `NAV_ACC_RAD` and `RTL_MIN_DIST`, and at these defaults that range is empty ([source](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/src/modules/navigator/rtl.cpp#L596-L628)). |

Docs: [Return mode (multicopter)](https://docs.px4.io/main/en/flight_modes_mc/return.html), [Missions: acceptance radius](https://docs.px4.io/main/en/flying/missions.html).

This shows up in the logs: the mission asks for 20 m, and the highest point flown is 30.05 m (Gazebo) and 31.08 m (SIH), because the return leg climbs to `RTL_RETURN_ALT`. Both went a little over it, which is why the `stays_in_geofence` precondition adds a clearance. The SIH flight also drifted 0.98 m past W1 while climbing.

The home latitude and longitude must be known before the run, so they come from the simulator's configured start position: `base_lat_lon` in the config, which is quick-setup's default. Takeoff's params point at it. The log's `home_position` can confirm them afterwards. The helper that turns waypoint positions in metres into latitude and longitude (`metres_to_lat_lon` in `helpers`) is still to write. Its formula, flat earth on PX4's sphere, gives `missions/simple.plan`'s W1 (50 m north) to the last digit. PX4's own `MapProjection::reproject` agrees with it to a few millimetres within the flight area. The `.plan` file's `plannedHomePosition` takes an altitude above sea level as its third value, which is not our z of 0. Our `simple.plan` has 0 there and `medium.plan` has 491. The plan step writes `plannedHomePosition` from `base_lat_lon` (lat, lon, alt). Its `alt` of 0 is the elevation of Gazebo's default world, and the `plannedHomePosition` height in `simple.plan` and `survey.plan`. The same point is the home in our three plans. If any of `PX4_HOME_LAT`, `PX4_HOME_LON` and `PX4_HOME_ALT` is set, PX4 needs all three (`px4-rc.gzsim`).

## 5. Tolerances: what the logs show

The tolerance values in `px4.yaml` are decided. Requirements are chosen, and noise allowances come from baseline runs (ADR 0005). This section is the evidence behind them. The noise allowances are provisional until ADR 0005's first 10-run baseline per setup. Counts are complete Gazebo flights at 4x unless a line says otherwise.

| Measured, complete Gazebo flights at 4x | fca3df865a (the pin) | 6d1773f4c1 (PX4's Docker image) |
|---|---|---|
| Closest approach to a held waypoint | 0.007 to 0.266 m (16) | 0.013 to 0.279 m (12) |
| Height error while holding | up to 0.091 m (16) | up to 0.056 m (12) |
| End distance from the goal | 0.019 to 0.069 m (16) | 0.018 to 0.085 m (12) |
| End speed | 0.00 m/s (16) | 0.00 m/s (12) |
| Highest point minus the 30 m return climb (waypoints below 30 m) | +0.013 to +0.059 m (9) | −0.033 to +0.054 m (3) |
| Closest approach during the hold stretch | 0.034 to 0.332 m (16) | 0.025 to 0.320 m (12) |
| Log ground truth against Gazebo's recording | not flown | up to 5.2 µm (5 with a full recording) |

Every number in this table comes from one script, `reviews/2026-11-23/evidence.py` in the local prototype, over 28 complete flights.

**Which flights are the baseline** (R8). Every flight below ran unmodified PX4 in Gazebo at 4x, with the 2 m acceptance radius in the plan. The runs are listed in `reviews/2026-11-23/evidence_inputs.txt` in the local prototype.

| Mission and plan | Hold flown | fca3df865a | 6d1773f4c1 | Role |
|---|---|---|---|---|
| M01 fixture (`tests/fixtures/m01/mission.plan`: W1 50 m north, 20 m up) | 5 s, as the mission asks | 3 (R02, smoke S01, S02cam) | 3 (smoke D01, spike GZ01, GZ02) | Passing reference runs |
| Generated M02, seed 7, current generator (W1 at 66.4, 92.4, 34.3 m) | 5 s, as the mission asks | 3 | 3 | Passing reference runs |
| The same mission, with the hold cut | 4 s | 2 | 3 | Stand-ins for a variant that cuts the hold; expected to fail the 5 s hold |
| The same mission, with the hold cut | 2 s | 2 | 3 | The same |
| Generated M02, seed 7, an earlier generator (W1 at −153.7, 119.5, 7.2 m): a different mission | 5 s | 2 | 0 | Passing reference runs |
| That earlier mission, with the hold cut | 2 s | 2 | 0 | Stand-ins for a variant that cuts the hold |
| Generated M01, seeds 1 and 2 | 5 s, as the mission asks | 2 | 0 | Passing reference runs |

**Not in the baseline:**
- **The two simple-mission logs in the tables above** (Gazebo and SIH). They were flown with PX4's default 10 m acceptance radius, before the plan carried 2 m, and SIH isn't the baseline simulator (`sim` in `px4.yaml`).
- **The survey trace from `ulog-extract-demo`:** the same default radius.
- **The earlier medium-style and survey flights with the 2 m radius:** their logs aren't in the input list.

Medium and survey have no reference runs under these rules yet.

**Time near W1.** W1 is at (50, 0, 20) and the plan tells PX4 to hold 5 s. The table gives the time spent near W1, measured two ways. For the single unbroken visit in each case, subtract the first inside timestamp from the next outside timestamp. This estimates the crossing times to sample resolution. The nominal interval is 0.02 s, with gaps up to 0.04 s in Gazebo.

| Distance | Gazebo, 3D | SIH, 3D | Gazebo, horizontal + height within 0.8 m | SIH, horizontal + height within 0.8 m |
|---|---|---|---|---|
| 2 m | 3.84 s | 4.04 s | 3.36 s | 3.52 s |
| 3 m | 4.80 s | 4.86 s | 3.94 s | 3.96 s |
| 5 m | 6.48 s | 6.34 s | 4.78 s | 4.66 s |
| 10 m | 13.29 s | 11.46 s | 6.04 s | 5.96 s |

- **The two measures disagree at 5 m.** A five-second hold passes by straight-line distance and fails by the second measure. Decided: the second measure, with separate horizontal and height limits (`tolerances.at_waypoint`).
- **The straight-line numbers include part of the return.** The return starts with a climb straight up from 20 m to 30 m above W1, so the drone stays "near" W1 after it has stopped holding. The second measure uses separate horizontal and height limits, like the PX4 arrival check.
- **PX4 switched to return** 4.96 s (Gazebo) and 5.08 s (SIH) after first coming within 10 m and 0.8 m of W1. See "What the 5 s hold actually does" below.
- **"Visited" passes either way in these two flights.** The closest the drone got to W1 was 0.22 m (Gazebo) and 0.36 m (SIH). Both hold at W1. Medium and survey give every waypoint a hold of 0. With the 2 m radius, three medium-style flights passed 0.48 to 1.14 m from each fly-through waypoint, with 23 to 30 log samples inside each zone at 4x.
- **Sim speed changes the sample spacing in Gazebo.** In a local Docker trial of mine the gap between log samples was 0.02 s at 1x, 0.07 s at 4x and 0.14 s at 8x. SIH stayed at 0.02 s even at 10x. At 4x the log also drops a sample now and then: one 0.136 s gap in 15,247 samples across 11 native flights on the pin (`sim-spikes/2026-11-22-baseline-check`). It fell while the drone was still at W1, just after PX4 had switched to the return. Position readings now come from Gazebo's recording, which is also 0.068 s apart at 4x; none over 0.076 s, log or recording, has been seen in the 28 baseline flights. `tolerances.log_gap_max_s` (0.2 s) covers one dropped sample in either. 0.136 s is more than half of 0.2 s, so ADR 0005's investigate rule applies before the first baseline. At 8x one dropped sample would be longer than 0.2 s, so flying faster than 4x needs a bigger allowance.
- **Plan positions and Gazebo positions differ a little.** The plan step turns metres into latitude and longitude on PX4's sphere (`metres_to_lat_lon`), and Gazebo uses WGS84. Measured as the mean east-west offset over a hold's samples moving slower than 0.3 m/s, in 14 local flights with a waypoint 92 to 143 m east or west of the base the held position sat 0.19 to 0.36 m further out than planned: 69 to 96% of what WGS84 predicts there (0.27 to 0.42 m), with the 4 s holds at the low end. WGS84 predicts 0.59 m at 200 m. One flight at 46 m sat 0.02 m out, against 0.14 m predicted. The held position also sits short of the waypoint on the north axis: 0.04 to 0.18 m in 20 of those 21 flights with a slow hold, where WGS84 predicts at most 0.02 m. That shortfall isn't WGS84, and an offset like it may be inside the east figure too, so WGS84 is a likely part of the east offset, not shown to be most of it. It fits inside `within_m`, so the sphere stays: it matches PX4 and our plans exactly.
- **A log gap during a hold (decided: `hold_at.max_gap`, `tolerances.log_gap_max_s`).** If the log skips more than 0.2 s during a stretch at the waypoint, that stretch doesn't count. A stretch that already proves the hold stays a PASS. With no such stretch, a log with a skip anywhere gives INCONCLUSIVE and not FAIL, to keep the rule simple: a FAIL needs a log with no holes. A stretch still open when the log ends counts up to its last sample.

**What the 5 s hold actually does.** With `goto`'s acceptance radius at 0, PX4 counts W1 reached as soon as the drone is within `NAV_ACC_RAD` (10 m) and starts the 5 s from there. The drone is still doing about 5 m/s at that moment. It spends the 5 s slowing down on its way in, arrives, and starts climbing for the return straight away.

| Time after entering the 10 m zone | Gazebo: distance, speed | SIH: distance, speed |
|---|---|---|
| 0 s | 9.9 m, 5.0 m/s | 10.0 m, 4.6 m/s |
| 2 s | 3.2 m, 2.1 m/s | 3.0 m, 2.5 m/s |
| 4 s | 0.7 m, 0.6 m/s | 0.1 m, 0.7 m/s |
| ~5 s, PX4 switches to return | 0.3 m, 0.25 m/s | 0.5 m, 0.3 m/s |
| 6 s | climbing at 2.0 m/s | climbing at 1.4 m/s |

The longest time within 10 m sideways and 0.8 m in height of W1 while moving slower than 0.5 m/s horizontally is 1.82 s (Gazebo) and 1.58 s (SIH). So none of these hold checks works with the plan as flown:

- Within PX4's own zone (10 m, 0.8 m) for 5 s passes (6.04 s, 5.96 s), but it measures the approach. A variant that creeps in slowly would pass without ever stopping.
- Within 2 m for 5 s fails both correct flights (3.36 s, 3.52 s).
- Nearly still for 5 s fails both correct flights (under 2 s).

The decision: one "at the waypoint" zone (`tolerances.at_waypoint`, 2 m sideways and 0.8 m in height), written into `goto`'s acceptance radius and used by `visited` and the hold check. PX4 then only starts the hold once the drone is within 2 m, and the drone keeps closing in during it. The hold check is the longest unbroken time in that zone while PX4 is flying the mission.

**Flown twice (Gazebo at 4x, local runs of mine).** A 5 s hold measured 6.11 s and 6.05 s in the zone. PX4 started its 5 s within 0.1 s of the drone entering the zone, and the drone was nearly still (under 0.5 m/s) for 4.48 s and 4.35 s, against under 2 s before. About 1.1 s of the measured time came after PX4 switched to the return, while the drone climbed out through the top 0.8 m of the zone.

**Why the hold only counts in mission mode.** Counting from the first reading inside the zone to the first reading outside also counts the time the drone takes to leave after PX4 starts the return. Eight more local flights with holds of 0 to 4 s read the hold asked for plus 1.06 to 1.11 s, so a 4 s hold measured 5.06 s and 5.11 s and passed a 5 s requirement. In 28 later local flights (Gazebo at 4x, two models) it added 1.11 to 1.33 s when the return climbed out of the zone and 1.78 to 1.87 s when it left sideways (a waypoint above `RTL_RETURN_ALT`). Counted only while PX4 is in mission mode (`vehicle_status.nav_state` 3), the same 28 flights read (`reviews/2026-11-23/evidence.py` in the local prototype):

| PX4 build | 5 s holds | 4 s holds | 2 s holds |
|---|---|---|---|
| fca3df865a (the pin) | 4.964 to 5.236 s (10 flights) | 4.148 s (2) | 2.040 to 2.112 s (4) |
| 6d1773f4c1 (PX4's Docker image) | 4.956 to 5.168 s (6) | 4.080 s (3) | 2.108 to 2.112 s (3) |

That is the planned hold −0.05 to +0.24 s, whichever way the drone leaves. With `tolerances.hold_short_by_s` at 0.25 s, every 5 s flight passes a 5 s requirement and every 4 s flight fails it. 0.25 s covers the worst short reading (0.044 s), with room for one dropped log sample at 4x (0.136 s). The M01 fixture's R02 reads 5.03 s (6.11 s before). A stretch ends at the first reading outside the zone or after the mode change; the mode at a reading is the last `nav_state` at or before it, and `vehicle_status` is logged about every 0.5 s and on every change (the return started 12 ms after the mission ended in the logs checked).

- **Counting only while nearly stopped** (under 0.3 m/s) was also tried. It reads 1.1 to 1.7 s short and depends on how the drone arrives, so it was not adopted.
- **Elsewhere:** PX4's own tests check a mission only while its item index is in range, ArduPilot's `wait_waypoint` fails if the vehicle leaves AUTO, and PGFuzz counts a hold only in LOITER.
- **A variant can't gain by faking the mode.** `nav_state` is PX4's own report, but the mode condition only ever shortens a stretch. A variant that claims it is still in mission mode gets at most what the zone alone would give.

**`at_goal.within_m`.** The goal state says the drone ends at (0, 0, 0). It ended 0.08 m away in the Gazebo log and 0.28 m away in the SIH log. An exact comparison would fail both. Seventeen more Gazebo flights from a local trial of mine (a newer v1.18 release candidate, in PX4's Docker image) ended 0.01 to 0.09 m away. **Decided: 0.5 m** (a requirement, ADR 0005). Across 28 complete Gazebo flights of mine (11 native on the pin at 4x, 17 in Docker on 6d1773f4c1 at 1x to 8x) the furthest end point was 0.09 m from the base, so 0.5 m leaves room without letting a landing somewhere else pass. A flight with GPS switched off in the air ended 6.92 m away. SIH lands less precisely, up to 1.09 m off at 10x speed, so it would need a larger value.

**At rest.** SIH's final velocity rounds to zero on each axis but its north component is about 2.43 × 10⁻⁸ m/s. A goal velocity needs its own comparison in m/s. **Decided: at rest means slower than 0.1 m/s** (a requirement). Every complete flight logged so far ended at 0.00 m/s.
