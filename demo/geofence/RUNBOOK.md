# Geofence demo (M02)

The verifier catching a real fault: the same mission flown twice, once as configured and once with PX4's return height set too high. The generator's precondition and the verifier's postcondition both use the mission's geofence, a 60 m by 35 m cylinder around the base. PX4's own geofence is off (`GF_MAX_*_DIST: 0`); PX4 never sees ours.

It runs on `dev`, which has every piece: the plan step, the log reader, #30's harness with its macOS fixes, and the verifier (#31). Run everything from the repo root with `.venv/bin/python`. To fly on macOS that is Python 3.14 from Homebrew, with system site-packages for Gazebo's bindings, plus pymavlink, protobuf 7.36.2 and `requirements-dev.txt`.

## 1. The precondition (live, instant)

A fence too low for PX4's 30 m return climb, plus 2 m clearance, is refused before anything flies:

```sh
.venv/bin/python scripts/generate_mission.py tests/fixtures/m01/start.xml demo/geofence/geofence-too-low.yaml platform_configs/px4.yaml --output-dir /tmp/refused --seed 4
```
→ `postconditions.stays_in_geofence.max_height_m 30.0 leaves no room for the return climb to 30.0 m with 2.0 m clearance`

At 35 m it's accepted, and the waypoint is drawn inside the fence. Seed 4 puts W1 55.3 m out, 16.1 m up:

```sh
.venv/bin/python scripts/generate_mission.py tests/fixtures/m01/start.xml demo/geofence/geofence.yaml platform_configs/px4.yaml --output-dir demo/geofence/M02 --seed 4
.venv/bin/python -m plan_step demo/geofence/M02 --settings demo/geofence/geofence.yaml --out demo/geofence/M02/mission.plan
```
Three items: take off to 16.1 m, go to W1 and hold 5 s, return home.

## 2. The postcondition (recorded runs; live is optional)

```sh
.venv/bin/python demo/geofence/show.py runs/M02/R01/verdict.json runs/M02/R02/verdict.json
```

| Run | PX4 setup | Highest point | Verdict |
|---|---|---|---|
| R01 | `platform_configs/px4.yaml` (`RTL_RETURN_ALT` 30) | 30.0 m | **PASS**, all 6 checks |
| R02 | `demo/geofence/px4-fault.yaml` (`RTL_RETURN_ALT` 45; only the harness gets it) | 45.0 m | **FAIL** on `stays_in_geofence` alone: "Left geofence at 47.120 s: 55.31 m horizontal (limit 60 m), 35.02 m height (limit 35 m)". The visit, hold, goal, disarm and cross-check all pass |

The story: the generator promised the return climb (to PX4's 30 m) fits under the fence, and the verifier checked the flown path against the same fence. With the autopilot configured differently, the promise broke and only that check failed. PX4's docs give 60 m as the default; our build sets 30 for multicopters. The fault is visible in the evidence: `run.json`'s `record.parameters.RTL_RETURN_ALT` is 45 and the run folder's `px4.yaml` copy says so.

To fly both again, about 2 minutes each, one after another. Each run goes through `scripts/run_mission.py`, which plans, flies, reads and verifies it:

```sh
PX4_DIR=/path/to/PX4-Autopilot demo/geofence/fly_both.sh
```
- The first run copies `demo/geofence/M02` to `runs/M02`, which git ignores, and the runs land in `runs/M02/R01` and `R02`. Delete `runs/M02` to fly from scratch.
- `fly_locked.py` takes a flight lock and waits for any running PX4 or Gazebo, so two flights never overlap. To share another tool's lock, set `HYDRA_FLIGHT_LOCK` to its lock file.

## Known gaps

- **PX4's return near home:** PX4 lowers the climb home only when the return starts within `RTL_MIN_DIST` (10 m) of the base. Further out, it climbs to the full `RTL_RETURN_ALT` (`src/modules/navigator/rtl.cpp`, `computeReturnAltitude`, at the pin). The return can start up to `NAV_ACC_RAD` (10 m) short of W1, so the fault shows only with W1 more than about 20 m out. Seed 4's is 55 m out. None of `RTL_MIN_DIST`, `RTL_CONE_ANG` or `NAV_ACC_RAD` is in `px4_setup` or any `relies_on` yet.
