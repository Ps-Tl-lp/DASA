# PX4 mappings: the detail behind `px4.yaml`

Nov 20, 2026. The blank "Team check" cells are for our row-by-row review.

**Reading this the first time:** go through the tables row by row. The bullets under each table and all of section 5 are backing detail: caveats and exact measurements from the two logs. Skip them at first and come back when a row raises a question.

**The two logs** are simple-mission flights from my local runs: `simple_gz_1.ulg` (Gazebo) and `simple_sih_1.ulg` (SIH, the simulator built into PX4). The mission is: take off to 20 m, fly 50 m north to W1, hold 5 s, return home and land.

Both logs were flown on PX4 build `fca3df865a`, the build the repo pins (ADR 0001). Doc links go to the latest PX4 docs, which can change. Two links go to that build's source code, for behaviour the docs do not describe.

## 1. State properties from the log

For a goal requirement, compare the flight evidence with the required value: PASS or FAIL when the evidence decides it, INCONCLUSIVE when it is missing or invalid. The final sample stands for the goal in these two logs because each holds one complete flight. If a log ends early or carries on into something else, its last sample does not show the mission's final state.

| Property | Log topic and field | Calculation | Why this field | Gazebo log | SIH log | Team check |
|---|---|---|---|---|---|---|
| `agent.x` | `vehicle_local_position_groundtruth.x` | value − first value | North position in metres. Ground truth is the simulator's own position, not PX4's estimate. | −0.08 | 0.26 | |
| `agent.y` | same topic, `y` | value − first value | East position in metres. | −0.02 | 0.09 | |
| `agent.z` | same topic, `z` | −(value − first value) | PX4's `z` is down, ours is up. | 0.00 | 0.00 | |
| `agent.velocity.x` | same topic, `vx` | value | North speed, m/s. | 0.00 | 0.00 | |
| `agent.velocity.y` | same topic, `vy` | value | East speed, m/s. | 0.00 | 0.00 | |
| `agent.velocity.z` | same topic, `vz` | −value | PX4's `vz` is down, ours is up. | 0.00 | 0.00 | |
| `agent.landed` | `vehicle_land_detected.landed` | last value | PX4's land detector: true once it judges the vehicle is on the ground. | true | true | |
| `waypoint.visited` | none: worked out from the path | came within `visit_distance_m` of the waypoint | The example checks recorded samples in a 3D sphere. A mission may still require takeoff, visit order or a continuous hold. | see section 5 | see section 5 | |

Docs: [VehicleLocalPosition](https://docs.px4.io/main/en/msg_docs/VehicleLocalPosition.html) (fields, units, and the list of topics that use it, including the ground-truth one), [VehicleLandDetected](https://docs.px4.io/main/en/msg_docs/VehicleLandDetected.html).

- **Why subtract the first value.** The simulator's origin need not be our (0, 0, 0). In both logs the first value is within 0.02 m of zero, so the subtraction is a safeguard. It does mean the mapping assumes the drone starts at home. A log that starts after liftoff, or a vehicle that starts elsewhere, needs a separately known home reference.
- **A start-state check on position would always pass,** because the first position is (0, 0, 0) by construction. Checking the start state against the log needs a different source for position.
- **Ground truth comes from the simulator.** A real vehicle lacks this simulator topic. PX4's estimated position is a different source of evidence.
- **`landed` and the disarm check below are PX4's own reports.** Position is the simulator's. If a variant could be wrong about having landed, that matters. Worth a team decision. A simulator-side version is possible: on the ground and still, from ground truth. Both flights end at height 0.00 m and speed 0.00 m/s.
- **A vehicle can be landed without ever flying.** In a never-armed log I had locally (`unkown_mission.ulg`, not a team file), `landed` stays true. If takeoff is required, check that the vehicle left the ground during this run.
- **Time** in the helpers is the message `timestamp` divided by 1,000,000: seconds since PX4 started.

### Declarations and candidate mappings

| Property | Candidate | On the two logs | Doc |
|---|---|---|---|
| `agent.has_camera`, `agent.has_grippers` | Declared in the start state, not read from the log. | Nothing shows what is fitted. `PD_GRIPPER_TYPE` reads 0 ("Binary Grab/Release") with no gripper on the vehicle, so it cannot confirm one. | [Gripper](https://docs.px4.io/main/en/peripherals/gripper.html) |
| `agent.is_carrying` | The last `gripper.command` after arming (0 = grab, 1 = release) records the request. Actual payload needs independent evidence. | One grab at boot on a vehicle with no gripper. No command after arming. | [Gripper message](https://docs.px4.io/main/en/msg_docs/Gripper.html) |
| `agent.was_attacked` | A `vehicle_command` 420 (inject failure) with a failure type other than 0. | No such request recorded. | [Failure injection](https://docs.px4.io/main/en/debug/failure_injection.html), [MAV_CMD_INJECT_FAILURE](https://mavlink.io/en/messages/common.html#MAV_CMD_INJECT_FAILURE) |
| `waypoint.clicked_pic` | Candidate evidence is a capture event near the waypoint. Check its feedback source and match its timestamp to the local path. | No capture topic in either log. | [CameraCapture](https://docs.px4.io/main/en/msg_docs/CameraCapture.html) |
| `waypoint.has_package` | No source. | | |

A gripper command can occur without a gripper. Both logs also have a camera trigger-control command (2003) at mission end on vehicles without a camera. On the pinned PX4 build, `camera_capture.result` can be 1 for a trigger without shutter feedback. A missing capture topic also leaves the outcome unknown unless the run guarantees capture coverage. [PX4 camera feedback source](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/src/modules/camera_feedback/CameraFeedback.cpp#L92-L154)

The gripper codes differ by source. A grab is 1 in MAVLink command 211 and 0 in the PX4 `gripper` topic. For `was_attacked`, command 420 records a request. It doesn't establish that a failure took effect. The team still needs to define the property.

## 2. Evidence for postconditions

These are not state properties. They are what the verifier reads to check a postcondition.

| Postcondition | Log topic and field | Calculation | Gazebo log | SIH log | Team check |
|---|---|---|---|---|---|
| Disarms after landing | `vehicle_status.latest_disarming_reason` | last value equals 6 (PX4 disarmed itself after landing) | 6 | 6 | |
| Never enters the no-fly zone | none: worked out from the path | any recorded point inside the box fails. Passing also needs the stretches between samples checked, by a rule we have not agreed | helper not written | helper not written | |
| Five-second hold | none: worked out from the path | time between coming within `visit_distance_m` and leaving | see section 5 | see section 5 | |
| No collision or crash (candidate) | four sources, see below | four warning signs, not enough to clear a flight | no signs | no signs | |
| Time limit (candidate) | `vehicle_status.arming_state` | time from arming to disarming | 78.0 s | 85.6 s | |
| Battery limit (candidate) | `battery_status.remaining` | lowest value while armed (0 to 1) | 0.50 | 0.50 | |

Docs: [VehicleStatus](https://docs.px4.io/main/en/msg_docs/VehicleStatus.html), [BatteryStatus](https://docs.px4.io/main/en/msg_docs/BatteryStatus.html).

- **Disarming.** Reason 6 means PX4 disarmed itself after detecting a landing. That numbering is from the pinned build and matches the current docs. PX4 v1.13 to v1.16 used 7 for it, and 6 meant the safety button. In both flights `landed` turns true about two seconds before the disarm (97.02 s then 99.03 s in Gazebo, 90.28 s then 92.30 s in SIH). Two limits: a disarm sent by command has a different reason, and the last reason alone does not show whether the vehicle armed again. If either matters, check the order of events instead: left the ground, landed, then armed to disarmed.
- **Collision or crash.** The four signs are the disarm reason, failure-detector flags, freefall, and final ground-truth tilt. In a separate local test run of mine (`contact2_1`), Gazebo recorded a rotor touching a box at 34.9 s. That flight's log still shows a landing disarm, clear flags, no freefall and 0° final tilt. So the four signs cannot clear a flight of a collision. The simulator's own contact record can show one. The two demo flights ended at 0.0° and 2.7°. The pinned build has `fd_roll` and `fd_pitch`. The [current message](https://docs.px4.io/main/en/msg_docs/FailureDetectorStatus.html) lists `fd_tilt`.
- **Battery: read the lowest value, not the last.** PX4 reserves −1 for an invalid fraction. Missing coverage cannot clear a battery limit. The reported fraction recovers after disarming, to 0.80 and 0.78 by the end of the logs. See also the 50% floor in section 3.
- **Time and battery limits are not demo postconditions.** The mappings are here because they were cheap to check. The limits themselves would be written with the postconditions.
- **The hold needs a required value too.** The verifier measures a hold time. Use the five seconds specified for the simple mission. Where to store that requirement for the plan step and verifier is still open.

## 3. Preconditions from PX4 parameters

The generator reads the two named PX4 limits from the intended run settings before flight. The values below come from the saved ULogs.

| Parameter | In both logs | What it limits | Used in config as |
|---|---|---|---|
| [GF_MAX_HOR_DIST](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#GF_MAX_HOR_DIST) | 0 (off) | Furthest horizontal distance from home before PX4's geofence acts | `max_distance_from_home` |
| [GF_MAX_VER_DIST](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#GF_MAX_VER_DIST) | 0 (off) | Greatest height above home before PX4's geofence acts | `max_height_above_home` |

- **Position ranges are blank.** Both geofence limits were disabled in these runs. The numbers are the team's to choose and to give a reason for.
- **These two limits are a circle and a height.** An x range and a y range cannot describe them, which is why they are under `other_constraints`. See [Safety: geofence](https://docs.px4.io/main/en/config/safety.html).
- **PX4 already blocks some missions itself.** It will not start a mission whose items conflict with a geofence, or one missing a takeoff or landing item when `MIS_TKO_LAND_REQ` asks for them. A first waypoint further than `MIS_DIST_1WP` from home only gets a warning. See [Mission mode: feasibility checks](https://docs.px4.io/main/en/flight_modes_mc/mission.html). Our generator could lean on this or copy it. Not decided.
- **A log does not record every parameter.** `MIS_TKO_LAND_REQ` and `MIS_DIST_1WP` are in the SIH log and absent from the Gazebo log. A setting the log does not record cannot be confirmed from it.
- **Speed limits are not in the config.** A start state and a goal state are both at rest, so a speed range has nothing to limit yet. If one is needed later, note that [MPC_XY_VEL_MAX](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MPC_XY_VEL_MAX) (12 m/s in both logs) is a configured limit on commanded horizontal speed. Mission cruise speed comes from [MPC_XY_CRUISE](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MPC_XY_CRUISE) (5 m/s in both logs, and the fastest flown was 5.06 m/s). A measured speed can also pass its parameter: [MPC_Z_VEL_MAX_DN](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#MPC_Z_VEL_MAX_DN) is 1.5 m/s and the SIH flight descended at 1.70 m/s.
- **A candidate not in the config:** `MIS_TAKEOFF_ALT` (2.5 m in both logs). The mission-mode page calls it the minimum takeoff altitude, the parameter reference calls it the default. Check before using it as a lower bound on takeoff height.

The three under `not_modelled_yet`:

- **Can arm.** PX4 reports this at the start of a run (`vehicle_status.pre_flight_checks_pass`, 1 in both logs). It is a check on the run. Nothing in a generated mission's values decides it.
- **Enough battery for the trip.** The simulated battery stops draining at 50% by default ([Simulate failsafes](https://docs.px4.io/main/en/simulation/failsafes.html)), and the measured minimum rounds to 0.50 on both flights. A battery condition below that cannot fail in the default simulator.
- **A path exists.** Testing the planned legs against the boxes can reject an obvious crossing. PX4 can round turns and climb on return, so clear waypoint-to-waypoint segments cannot certify the flight path. [Mission mode](https://docs.px4.io/main/en/flight_modes_mc/mission.html)

## 4. Tasks to plan items

### How the plan step is meant to use `tasks`

This is our assumption and has not been settled. A task's `sets` says what state change it is for, and its `needs` says what must be true first. The plan step works forward from the start state until it reaches the goal state.

The simple mission as an example. The start and goal states differ in one property: `waypoint.W1.visited` goes from false to true.

1. `goto` sets `visited` to true. It needs `agent.landed` to be false, so `takeoff` goes first.
2. After `goto` the agent is at W1 and in the air. The goal state has it at its base and landed, so `return_home` goes last.

Result: `takeoff`, `goto W1`, `return_home`. Those are the three items in our `simple.plan`.

- **The difference between start and goal is not enough by itself.** Takeoff and return leave no net change in the states. They come from `needs` and from where the goal state says the agent ends.
- The plan step still needs waypoint order, takeoff height and hold time.

The medium mission adds an order requirement. Its fourth waypoint has the same coordinates and altitude as the takeoff item. Checking each waypoint's first visit could put W4 first on a correct run. Look for a qualifying W4 visit after W3. The survey plan has 12 waypoint items defining its lawnmower route.

No task here lands away from home. `return_home` is the only task that sets `agent.landed` to true. Landing elsewhere would need a land task (MAVLink command 21).

### The plan items

`command` and `frame` are numbers from MAVLink, the message format PX4 and ground stations share. `params` is the seven-slot list each `.plan` item carries.

| Task | Command | Frame | What the params carry | Team check |
|---|---|---|---|---|
| `takeoff` | 22, [MAV_CMD_NAV_TAKEOFF](https://mavlink.io/en/messages/common.html#MAV_CMD_NAV_TAKEOFF) | 3 | 5 and 6: latitude and longitude. 7: height. | |
| `goto` | 16, [MAV_CMD_NAV_WAYPOINT](https://mavlink.io/en/messages/common.html#MAV_CMD_NAV_WAYPOINT) | 3 | 1: hold time in seconds. 2: acceptance radius (ours is 0, so `NAV_ACC_RAD` applies). 5 to 7: latitude, longitude, height. | |
| `return_home` | 20, [MAV_CMD_NAV_RETURN_TO_LAUNCH](https://mavlink.io/en/messages/common.html#MAV_CMD_NAV_RETURN_TO_LAUNCH) | 2 | Nothing. The demo assumes RTL_TYPE 0, no rally points and automatic landing enabled. | |

- **Frame 3** means latitude and longitude with height measured from home. **Frame 2** is MAV_FRAME_MISSION. RTL has no position arguments. See [MAV_FRAME](https://mavlink.io/en/messages/common.html#MAV_FRAME).
- The three items match our own `simple.plan` item for item: same commands, frames and param layout.
- PX4's reading of each command's params is in [VehicleCommand](https://docs.px4.io/main/en/msg_docs/VehicleCommand.html). The item keys in `plan_item_defaults` are from the [QGroundControl plan format](https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/file_formats/plan.html). Our `simple.plan` uses `AltitudeMode: 1` with `Altitude` equal to param 7. The medium plan omits both keys on RTL.
- **The hold time in the plan is a command to PX4.** The PX4 docs describe param 1 as time to stay inside the acceptance radius ([NavigatorMissionItem](https://docs.px4.io/main/en/msg_docs/NavigatorMissionItem.html), `time_inside`). The pinned build does something slightly different: it marks the waypoint reached once, then counts from that moment without checking the drone is still inside ([source](https://github.com/PX4/PX4-Autopilot/blob/fca3df865af36124a28c9d607e850f111dbaaea9/src/modules/navigator/mission_block.cpp#L380-L433)). Whether the drone held for five seconds by our definition is a separate question (section 5).

`relies_on` lists the parameters that change what an item does:

| Parameter | In both logs | What it changes |
|---|---|---|
| [NAV_ACC_RAD](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#NAV_ACC_RAD) | 10 m | How close PX4 counts as having reached a waypoint, unless the item gives its own radius |
| [NAV_MC_ALT_RAD](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#NAV_MC_ALT_RAD) | 0.8 m | The same, for height |
| [RTL_TYPE](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_TYPE) | 0 | Where a return goes. 0 is home, or a rally point (an alternative landing spot) if one is closer. Our plans have none. |
| [RTL_RETURN_ALT](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_RETURN_ALT) | 30 m | The drone climbs to this height before flying back, unless it is already higher |
| [RTL_DESCEND_ALT](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_DESCEND_ALT) | 10 m | The height it drops to over home before landing |
| [RTL_LAND_DELAY](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_LAND_DELAY) | 0 s | The wait at that height before landing. −1 means hover and never land. |
| [RTL_MIN_DIST](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_MIN_DIST), [RTL_CONE_ANG](https://docs.px4.io/main/en/advanced_config/parameter_reference.html#RTL_CONE_ANG) | 10 m, 45° | Close to home, the return height can be lower than `RTL_RETURN_ALT` |

Docs: [Return mode (multicopter)](https://docs.px4.io/main/en/flight_modes_mc/return.html), [Missions: acceptance radius](https://docs.px4.io/main/en/flying/missions.html).

This shows up in the logs: the mission asks for 20 m, and the highest point flown is 30.05 m (Gazebo) and 31.08 m (SIH), because the return leg climbs to `RTL_RETURN_ALT`.

`$home_lat` and `$home_lon` must be known before the run, so they come from the simulator's configured start position. The log's `home_position` can confirm them afterwards. The helper that turns waypoint positions in metres into latitude and longitude is still to write. The `.plan` file's `plannedHomePosition` takes an altitude above sea level as its third value, which is not our z of 0. Our `simple.plan` has 0 there and `medium.plan` has 491.

## 5. Tolerances: what the two logs show

The tolerance values are still open.

**`visit_distance_m`.** W1 is at (50, 0, 20) and the plan tells PX4 to hold 5 s. The table gives the time spent near W1, measured two ways. For the single unbroken visit in each case, subtract the first inside timestamp from the next outside timestamp. This estimates the crossing times to sample resolution. The nominal interval is 0.02 s, with gaps up to 0.04 s in Gazebo.

| Distance | Gazebo, 3D | SIH, 3D | Gazebo, horizontal + height within 0.8 m | SIH, horizontal + height within 0.8 m |
|---|---|---|---|---|
| 2 m | 3.84 s | 4.04 s | 3.36 s | 3.52 s |
| 3 m | 4.80 s | 4.86 s | 3.94 s | 3.96 s |
| 5 m | 6.48 s | 6.34 s | 4.78 s | 4.66 s |
| 10 m | 13.29 s | 11.46 s | 6.04 s | 5.96 s |

- **The two measures disagree at 5 m.** A five-second hold passes by straight-line distance and fails by the second measure. The team has to choose the measure as well as the distance.
- **The straight-line numbers include part of the return.** The return starts with a climb straight up from 20 m to 30 m above W1, so the drone stays "near" W1 after it has stopped holding. The second measure uses separate horizontal and height limits, like the PX4 arrival check.
- **PX4 switched to return** 4.96 s (Gazebo) and 5.08 s (SIH) after first coming within 10 m and 0.8 m of W1. Those times do not establish five continuous seconds under a HYDRA hold rule. Decide whether the rule means occupancy alone or holding during the waypoint task.
- **"Visited" passes either way in these two flights.** The closest the drone got to W1 was 0.22 m (Gazebo) and 0.36 m (SIH). Both hold at W1. Medium and survey give every waypoint a hold of 0, and this section has no evidence for a waypoint the drone flies through.
- `helpers_example.py` measures straight-line distance.

**`goal_position_m`.** The goal state says the drone ends at (0, 0, 0). It ended 0.08 m away in the Gazebo log and 0.28 m away in the SIH log. An exact comparison would fail both.

**At rest.** SIH's final velocity rounds to zero on each axis but its north component is about 2.43 × 10⁻⁸ m/s. A goal velocity needs its own comparison in m/s.

## 6. How to repeat the check

```sh
pip install pyulog
python helpers_example.py simple_gz_1.ulg 50 0 20 5
```

That prints the final position and whether W1 was visited within 5 m. To reproduce a hold-table column, apply the method and region described in section 5. The script that produced the table is not in this folder.
