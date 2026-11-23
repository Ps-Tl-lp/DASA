# Platform configs

One file per platform. `px4.yaml` is the only one so far. It holds everything PX4-specific the pipeline needs: which drones exist, the rules a generated mission has to pass, how a task becomes a `.plan` item, what to read from the log, and how the readings are judged.

Values marked `PROPOSED` in the file are not decided yet. They are tracked in [docs/testing.md](../docs/testing.md#not-decided-yet).

## Who uses which part

| Part of `px4.yaml` | Used by | What it's for |
|---|---|---|
| `vehicle_types`, `px4_setup` | Generator, harness | Which drone flies, and the PX4 settings for every flight |
| `preconditions` | Generator | Rules a generated mission has to pass |
| `tasks`, `plan_item_defaults`, `plan_template`, `inputs` | Plan step | Which tasks a mission needs, how to write each into the `.plan` file, and where each `$` value comes from |
| `base_lat_lon` | Plan step, harness | Where the base is on the map |
| `readings` | Log reader | What we read from the log |
| `not_in_log`, `derived`, `goal_check`, `postconditions` | Verifier | How the readings are judged against the goal state and the postconditions |
| `helpers` | Whoever builds one | Every function the config names, who calls it and what it answers |
| `tolerances` | All of them | The shared numbers |

PX4 parameter names appear only in `px4.yaml`. The generator, the mission settings and the states stay platform-neutral. Another platform (ArduPilot) would need its own version of this file, plus its own plan writer and log reader if its plan or log format differs from PX4's.

## What lives where

| What it is | Lives in |
|---|---|
| A PX4 or simulator name or number | The config |
| A number or fact two programs must agree on | The config |
| Where a value comes from | The config |
| What this mission wants | The mission |
| How to work something out | Code. The config names the function (`helper:`) and says in one sentence what it must do (`rule:`) |

No module hard-codes a number, a PX4 name or a lookup. If a builder needs one that is missing, add it to the config.

The top of `px4.yaml` lists how values are written. `tests/test_px4_config.py` checks the main ones.

## How a mission goes through it

1. The generator reads a mission settings file (simple, medium or survey) and the ranges in `px4.yaml`. It picks a vehicle type and draws a start state and a goal state inside the flight area, and inside the mission's geofence if it has one. The settings also give the mission's postconditions, such as the hold at each waypoint. The generator writes them out next to the two states.
2. It checks the drawn mission (waypoint spacing, the geofence) and asks the plan step to build its plan. If anything fails, it draws again. The plan built for this check is the plan that gets flown.
3. The plan step compares the two states, picks the tasks that make the changes (`sets`) plus whatever has to happen first (`needs`), and writes the `.plan` file. The two states can't show a hold or an order, so it reads both from the mission's postconditions. `inputs` says where each value it fills in comes from.
4. The harness sets PX4 up (`px4_setup`), launches the vehicle type's `sim_model` in Gazebo, flies the plan and saves the `.ulg` log.
5. The log reader turns the log into `readings`, each sample with its time. That is all it does. It doesn't need the mission.
6. The verifier does all the judging. It works out `visited` and `clicked_pic` from the readings and the mission's waypoints, compares the end of the flight with the goal state, and checks each of the mission's postconditions, using the mission's values and not the plan's: PASS, FAIL or INCONCLUSIVE.

## Related

- [docs/px4-mappings.md](../docs/px4-mappings.md): where each row comes from (PX4 docs, the calculation, what test flights showed)
- [docs/definitions.md](../docs/definitions.md): what each term means
- [docs/adr/0004-platform-config.md](../docs/adr/0004-platform-config.md): why this lives in one file per platform
