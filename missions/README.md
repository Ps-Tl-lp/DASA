# Missions

QGroundControl plans for the three fixed missions. A plan holds the verifier's expected values: a flight log is checked against the plan that was flown. `tests/test_missions.py` checks each plan against its definition below, and checks that each plan's home is the simulator's default launch point (quick-setup's `PX4_HOME_LAT` and `PX4_HOME_LON`).

| Plan | Definition |
|---|---|
| `simple.plan` | Take off to 20 m above home, fly to a point 50 m north of launch, hold 5 s, return to launch and land. |
| `medium.plan` | Fly at 20 m above home through north/east offsets (50, 0), (50, 50), (0, 50), (0, 0) m, in order, no dwell; then return to launch and land. |
| `survey.plan` | Fly at 30 m above home over a 100 m by 100 m rectangle: six 100 m transects spaced 20 m apart, connected through 12 alternating endpoints, spanning 20 to 120 m north and 20 to 120 m east of launch; then return to launch and land. The card calls it the complicated mission. |

The definitions are from the Trello card [Run the simple, medium, and survey missions](https://trello.com/c/4RkVc4r8/23-run-the-simple-medium-and-survey-missions) (team board).

The files are copied unchanged from `samples/plans/` in `dasa-capstone/ulog-extract-demo` (private, org members) at commit `eb07982`. The team's sample flights of these plans were flown in `dasa-capstone/quick-setup` (private, org members) at PX4 `fca3df865a` (v1.18.0-rc1).

`medium.plan` has a `plannedHomePosition` altitude of 491; `simple.plan` and `survey.plan` have 0. Every takeoff and waypoint item uses relative altitude (frame 3, metres above home), so the value doesn't change the mission. It is noted here, not changed.

Editing a plan is ask-first, because it changes what the verifier checks flights against. If a definition changes, update the plan, this table and the test in the same PR.
