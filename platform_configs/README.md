# HYDRA PX4 config proposal

Nov 20, 2026. My proposal for the team to pick apart. It covers the PX4 config for the Nov 24 demo, not the generator, plan step or verifier.

## What's in this folder

| File | What it is |
|---|---|
| `px4.yaml` | The proposed config. Start here. |
| `MAPPINGS.md` | The source, calculation and flight evidence for each mapping. |
| `DEFINITIONS.md` | The terms we use in this proposal. |
| `whiteboard.png` | Our pipeline board. The three yellow boxes are this config. |
| `helpers_example.py` | The `visited` helper and the path reader it uses. |

## Who uses the config?

| Section | Used by | What it says |
|---|---|---|
| `preconditions` (proposed) | Generator | Which values to draw and which combinations to reject before flight. |
| `tasks` and `plan_item_defaults` | Plan step | What each task changes and how to write its QGroundControl `.plan` item. |
| `log_mappings`, `postcondition_evidence` and `tolerances` | Log reader and verifier | How to read the final state and flight path, and which comparisons still need a tolerance. |

The generator needs the simulator's effective PX4 settings **before** flight. Afterward, the ULog can confirm the settings it recorded for that run. The plan step also needs the home latitude and longitude before the run.

## Mission generation, as this proposal assumes it

The demo starts with one multicopter on the ground, at rest at home. The generator varies the mission properties that can change. It checks the proposed start/goal pair against the preconditions. The plan step still has to find tasks that produce the requested changes. Arming, battery sufficiency and path feasibility are still open.

One waypoint gives the shape of the simple mission. Reproducing the existing missions also takes a five-second hold for simple, four waypoints **in order** for medium, and an ordered lawnmower route for survey. So the existing missions are settings of one generator, not separate templates. Those settings are shared across platforms, which is why they are not in `px4.yaml`.

## What changed from my earlier proposal

- Preconditions are in this config, not in the mission file.
- The mission is a start state and a goal state, so the config no longer reads a route from the mission file.
- Takeoff, goto and return home are called *tasks*. PX4 decides how to fly them.
- The no-fly zone has no `entered` flag. The generator checks positions against it, and the verifier checks whether the flight entered it.
- One config file instead of two.

## Still open

- Where to keep generator settings, takeoff height, and the list of properties a mission may change. The plan step and verifier need the same required hold time. How to express waypoint order when a mission requires it is still open.
- Where the no-fly box belongs. Both steps need its geometry. The generator checks the selected positions and the verifier checks the flown path.
- How to pick tasks from the two states. Section 4 of `MAPPINGS.md` works through the simple mission using `sets` and `needs`. The demo only covers landing at home.
- Which position ranges and comparison tolerances to use. Section 5 shows that the way distance is measured changes the measured hold.
- Which evidence can establish a collision, a captured picture, a carried package or an attack. A start-state equipment declaration records what the mission assumes.
- Whether a postcondition must be checkable from the log alone. `DEFINITIONS.md` says it must, and the log cannot show a collision (section 2 of `MAPPINGS.md`). Either other flight evidence counts, such as the simulator's contact record, or "no collision" is not a postcondition.
- Whether `agent.landed` becomes a property. The config relies on it at the start and the goal.

The open decisions that touch the config are marked `PLACEHOLDER:` in `px4.yaml`.

## How far this was checked

The three command templates reproduce the items in `simple.plan`. The example helper runs on the saved Gazebo and SIH simple missions. Section 5 of `MAPPINGS.md` gives the measured distances and times. A separate Gazebo contact run shows a limit of the proposed collision checks.

All four of us still need to review the mappings row by row. Drafted with Claude and reviewed with Codex.
