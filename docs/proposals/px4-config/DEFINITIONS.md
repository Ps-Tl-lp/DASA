# Shared definitions

Working definitions for this proposal.

| Term | Meaning |
|---|---|
| Environment representation | Everything that can exist in a mission (agents, waypoints, other objects) and their properties, with no values. The same representation should work for another platform. |
| Property | One named value that a thing in the environment has, such as an agent's `x` or a waypoint's `visited`. The environment representation lists every property, and a state gives each one a value. Written as `thing.property`, for example `agent.x`. With an id when a mission has several: `waypoint.W1.visited`. |
| State | The environment with every property's value filled in, at one moment. |
| Start state | The state when the mission begins. |
| Goal state | The state we expect when the mission is done. Same properties as the start state. Only what the mission changes is different. |
| Mission | For this demo, one start state and one goal state, shown as two XML files on the board. A flight may also have requirements such as waypoint order and hold time. |
| Home | The demo agent's base and the origin (0, 0, 0) for its coordinates. The demo assumes the agent starts there. |
| Generator | Draws values for the properties allowed to vary and keeps only missions that pass the preconditions. What it produces is a start state and a goal state. Settings include the number of waypoints. |
| Precondition | A condition that must hold for the mission to be accomplishable. The generator checks it before accepting a mission. Some depend on a platform setting, such as maximum height. Others depend on the mission, such as staying outside a no-fly zone. Not written in the mission. |
| Accomplishable | The platform could complete the mission. A generated mission that breaks a precondition is discarded and never flown. Passing the checks we have only rules out the problems they cover. |
| Postcondition | A condition for success that the goal state cannot show, about the whole flight or its end. It must be checkable from the log. |
| No-fly zone | An area the drone must stay out of. Start and goal may not be inside it (precondition). The flight may not enter it (postcondition). Not the same as PX4's `GF_MAX_` limits, which are a cylinder to stay inside. |
| Task | What we ask the drone to do, such as go to waypoint A. Tasks go in the plan. |
| Action | How the drone does it: fly, turn, move. That is PX4's job and we do not model it. Takeoff, go to waypoint and return home are tasks, not actions. |
| Mission plan | The QGroundControl `.plan` file the plan step produces from the mission. |
| Plan step | The program that turns a mission into a mission plan. "Plan translator" on the whiteboard. |
| Mapping | How to get a property's value from the available evidence. Some mappings use one log field, others use the flown path. |
| Verifier | Checks the goal and postconditions against the flight evidence. Each requirement gets PASS, FAIL or INCONCLUSIVE. Use INCONCLUSIVE when the evidence cannot decide it. The board shows the log reader separately. |
| Validate | Show that the verifier gives the right answer on runs whose answer we already know. This is a working meaning and still open. |

## Words that are easy to mix up

- **Property** is ours: a value in the environment, such as `agent.x`.
- **Field** is the log's: a value inside a log message, such as `landed` in `vehicle_land_detected`.
- **Parameter** is PX4's: a setting on the vehicle, such as `NAV_ACC_RAD`.
- **`params`** in a plan item are the seven slots of one command. They are not PX4 parameters.

A mapping connects a property to a field. A precondition can connect a property to a parameter.

**Mission spec** has been used for three different things: the start and goal pair, the plan file, and a template for one kind of mission. Say mission, mission plan or generator settings instead.
