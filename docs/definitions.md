# Shared definitions

What we mean by these words across the repo. If one doesn't match how you use it, say so and we'll fix it.

| Term | Meaning |
|---|---|
| Environment representation | Everything that can exist in a mission (agents, waypoints, other objects) and their properties, with no values. The same representation should work for another platform. |
| Property | One named value that a thing in the environment has, such as an agent's `x` or a waypoint's `visited`. The environment representation lists every property, and a state gives each one a value. Written as `thing.property`, for example `agent.x`. With an id when a mission has several: `waypoint.W1.visited`. |
| State | The environment with every property's value filled in, at one moment. |
| Start state | The state when the mission begins. |
| Goal state | The state we expect when the mission is done. Same properties as the start state. Only what the mission changes is different. |
| Mission | For this demo, one start state and one goal state, shown as two XML files on the board. Requirements the two states can't show, such as hold time and waypoint order, are the mission's postconditions and travel with it. |
| Base | Where the agent launches and lands, and the origin (0, 0, 0) for its coordinates. The demo assumes the agent starts there. PX4 calls it home. |
| Generator | Draws values for the properties allowed to vary and keeps only missions that pass the preconditions. What it produces is a start state, a goal state and the mission's postconditions with their values filled in. Settings include the number of waypoints. |
| Precondition | A rule a mission must pass to be accomplishable. The generator only outputs missions that pass. Some are a single limit, like maximum height. Others need several values together, like waypoint spacing. They live in the platform config, not in the mission. |
| Accomplishable | The platform could complete the mission. A mission that breaks a precondition is never flown. Passing our checks only rules out the problems they cover. |
| Postcondition | A condition for success that the goal state can't show, because it's about the whole flight. Example: the drone never left the geofence. It must be checkable from what a run records: the log, and the harness's Gazebo recording. |
| Flight area | How far out the generator is allowed to place a mission: a cylinder around the base. Generated points can't be outside it. Our own limit; PX4 and Gazebo don't set one. |
| Geofence | An optional per-mission rule: a cylinder around the base the flight must stay inside. It comes from the mission's settings and fits inside the flight area. The same check runs twice: before the flight on where the plan will fly, with `tolerances.geofence_clearance_m` to spare (precondition), and after it on the flown path (postcondition). PX4 has its own geofence (`GF_MAX_` parameters); we keep that off. |
| At the waypoint | A short cylinder around a waypoint. Its size is `tolerances.at_waypoint` in `platform_configs/px4.yaml`: `within_m` sideways, `height_within_m` up or down. A position exactly on a limit counts as inside. Used for the plan's acceptance radius, `visited`, `clicked_pic`, the hold check and the order check. |
| Takeoff | The first airborne reading in the log. |
| Touchdown | The first landed reading after the last airborne one. `disarmed_after_landing` (in `platform_configs/px4.yaml`) checks that PX4 disarms at or after it. |
| Disarm | A change of PX4's `arming_state` from armed to disarmed. Its reason is the disarm reason PX4 records at that change. |
| Mission mode | PX4 flying the uploaded mission: `nav_state` 3 (`NAVIGATION_STATE_AUTO_MISSION`). The hold check counts only while PX4 is in it. |
| Stretch | An unbroken run of position readings inside a waypoint's zone while PX4 is in mission mode. It ends at the first position reading outside the zone or out of mission mode. |
| Harness | The program that sets PX4 and Gazebo up, flies the plan, records Gazebo's pose and saves the log, with a run record (`run.json`). |
| Flyer | The part of the harness that uploads the plan to PX4, arms, starts the mission and waits for the disarm. |
| Recording | The harness's record of Gazebo's pose of the vehicle, made outside PX4. Position, velocity and `landed` are read from it. |
| Sample | One timed value of a reading. |
| Reading | A value read from the log or from the harness's Gazebo recording, over the whole flight. Each reading names its source in `platform_configs/px4.yaml`. The verifier works from readings and never opens either file. |
| Vehicle type | A drone we can launch, with what it's fitted with (camera, grippers). Listed in `px4.yaml`. The generator flies the least-equipped one that can do the mission, and the start state copies its equipment. |
| Mission settings | What kind of mission to generate: how many waypoints, which properties change, any narrower ranges. Platform-neutral, kept with the generator. Can narrow `px4.yaml`'s ranges, never widen them. |
| No-fly zone | An area the drone must stay out of. Dropped for the demo (Nov 21). A rule, not a solid obstacle. |
| Task | What we ask the drone to do, such as go to waypoint A. Tasks go in the plan. |
| Action | How the drone does a task: fly, turn, climb. That's PX4's job. We only say what each task changes, not the path PX4 takes to do it. Takeoff, go to waypoint and return home are tasks, not actions. |
| Mission plan | The QGroundControl `.plan` file the plan step produces from the mission. |
| Plan step | The program that turns a mission into a mission plan. "Plan translator" on the board. |
| Mapping | How to get a property's value from the available evidence. Some mappings use one log field, others use the flown path. |
| Log reader | Turns the platform's log and the harness's Gazebo recording into timed readings, and checks the log's ground truth against the recording. It doesn't need the mission and judges nothing. |
| Verifier | Checks the goal and postconditions against the readings and the mission. Each requirement gets PASS, FAIL or INCONCLUSIVE. Use INCONCLUSIVE when the readings cannot decide it. |
| Validate | Show that the verifier gives the right answer on runs whose answer we already know. This is a working meaning and still open. |

## Words that are easy to mix up

- **Property** is ours: a value in the environment, such as `agent.x`.
- **Field** is the log's: a value inside a log message, such as `landed` in `vehicle_land_detected`.
- **Parameter** is PX4's: a setting on the vehicle, such as `NAV_ACC_RAD`.
- **`params`** in a plan item are the seven slots of one command. They are not PX4 parameters.
- **Entity** is anything in the environment representation that is not an agent, such as a waypoint. **Obstacle** is something solid the drone can hit. Avoid plain "object" for either.

A mapping connects a property to a field. A precondition can connect a property to a parameter.

**Mission spec** has been used for three different things: the start and goal pair, the plan file, and a template for one kind of mission. Say mission, mission plan or generator settings instead.
