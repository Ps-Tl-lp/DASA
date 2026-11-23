# Testing

How we test HYDRA's code, mainly the mission verifier.

## Running the checks

From the repo root, with the virtual environment active:

```sh
ruff check . && ruff format --check . && pytest     # the full check, same as CI
```

Setup and the other commands are in [CONTRIBUTING.md](../CONTRIBUTING.md#local-checks). CI (`.github/workflows/ci.yml`) runs `pytest` as the `test` job and both ruff commands as the `lint` job, on every pull request to `main`.

To run part of the suite, give pytest a file (`pytest tests/test_missions.py`) or part of a test name (`pytest -k survey`).

## Layout

- `tests/`: pytest tests in files named `test_*.py`. Name each test for the behavior it checks, such as `test_mission_ends_with_return_to_launch`.
- `tests/fixtures/`: small sample data the tests use, committed to git (none yet). Each fixture comes with a note saying where it came from: PX4 commit, simulator, mission plan, and how it was trimmed. Raw `.ulg` files and run results stay out of git; `.gitignore` ignores `*.ulg` everywhere except `tests/fixtures/`.
- `missions/`: the three mission plans. `tests/test_missions.py` checks each one against its written definition in [missions/README.md](../missions/README.md).
- `platform_configs/`: the PX4 config. `tests/test_px4_config.py` checks that it loads, that it keeps to its own rules for how values are written (every name it points at exists, every `$` value and helper is listed, every check has a rule and uses readings it defines), and that its tasks and plan item fields match `missions/simple.plan`. It does not check whether the values are right.

## Rules

- Every verifier change gets at least one PASS, one FAIL and one INCONCLUSIVE case.
- Expected results never come from the verifier's own output. A test that copies the verifier's answer only detects that the answer changed, not whether it is right. Build each case one of two ways:
  - By construction: synthetic data with a known answer, such as a hover just inside and just outside the arrival radius.
  - By mutating a known-good input: move a waypoint 20 m, swap two waypoints, lengthen a hold, cut a log short, or drop a topic. The spec says what the result must become.
- Validation is independent. The people testing the verifier are not the people building it (Trello card [Validate the verifier](https://trello.com/c/beYmLDIM), team board; Oct 20 meeting). Testers take expected results from the spec.
- Seed all randomness, so a failing run can be repeated.
- Before fixing a bug, write a test that reproduces it and fails. The fix makes it pass.
- A flaky test passes and fails on the same code. Quarantine it the day it appears: skip it with `@pytest.mark.skip(reason="flaky: <issue link>")`, open an Issue, and find the cause before deleting anything, because some flaky tests are reporting a real bug. Run a new test several times in a row before merging it.
- Never edit or delete a test to make it pass. If a test itself is wrong, say so in the PR and explain the change.
- Test behavior at the boundaries: one case just inside and one just outside each tolerance. For time limits, mind the 0.1 s resolution of ground truth (below).

## Known behaviors tests must account for

These are single-run observations: one flight per mission, in PX4 SITL with Gazebo `x500` at PX4 `fca3df865a`. Re-check them before a test depends on one, and again whenever the PX4 commit changes. Sources: the [verifier plan](https://docs.google.com/document/d/1xhm-_O4FKUWdXvWfAV6_XaXU9NsUcIitvYouGffeArI/edit) (Google Doc, team access), the Testing and CI research notes (Oct 22; see [sources](sources.md)), and the `dasa-capstone/ulog-extract-demo` README and sample traces (private, org members).

PX4 behavior:

- Corner cutting. PX4 counts a waypoint as reached within `NAV_ACC_RAD` (10 m in our logs) and turns early, so most waypoints were passed about 3.5 m off (2.5 to 5.2 m). An arrival radius under about 6 m fails our own baseline. The simple mission's hold waypoint was hit within 0.18 m.
- Dwell. PX4 starts the hold timer when it accepts the waypoint (within 10 m), so continuous time near the waypoint is shorter at tight radii. On simple, which asks for 5 s, the longest stretch within 2 m of the waypoint was 3.8 s, and within 10 m it was 6.4 s (altitude within 2 m in both). Cut at the RTL switch, the 10 m stretch is about 4.8 s: about 1.6 s of it came after RTL started, while the drone climbed in place.
- RTL timing. In medium and survey, PX4 switched to RTL about 0.1 s before ground truth entered the last waypoint's 10 m region, because PX4 goes by its own position estimate. A strict "RTL after the last arrival" check fails the baseline.
- `mission_result.seq_reached` skips the last waypoint (3 to 5 in medium, 11 to 13 in survey), so a cross-check against PX4's own verdicts always disagrees there.

Log contents:

- Matching traps. Medium's last waypoint is over the launch point, which the drone also passes on takeoff, and survey's return flight crosses the grid. Both fooled a closest-point search. In a throwaway proof of concept, taking the first entry after the previous waypoint's arrival handled both.
- Logs start differently. Medium's log starts before arming; simple's and survey's start already armed. Don't assume a log starts disarmed.
- Timestamps are uint64 microseconds since boot. Some samples come before the log start, so cast to signed before subtracting.
- Latitude and longitude need about 7 decimals. Three decimals is about 100 m.
- Local frames are NED: z points down, so altitude is -z.
- Ground truth is logged at about 10 Hz, so times measured from it have about 0.1 s resolution. Other topics log at other rates (EKF position about 125 Hz, `vehicle_status` about 2 Hz, `mission_result` only on change), so line them up by time, not by row.

## Not decided yet

This list is the one place open decisions are tracked. Until one is decided, code or a test that depends on it gets a clearly marked placeholder (a comment starting `PLACEHOLDER:` that names the open decision), and the PR lists it. Don't pick a value or rule silently.

- Tolerance values, and where they are defined. ADR 0004 proposes `platform_configs/px4.yaml`, and every value marked `PROPOSED` there is still open.
- How to show a picture was taken, not just that PX4 triggered the camera.
- What evidence can show a collision. The log can't; the simulator's contact record can.
- The never-lands rule: when a log that ends airborne counts as FAIL rather than INCONCLUSIVE.
- The RTL timing rule.
- The dwell window across the RTL switch. `platform_configs/px4.yaml` proposes one rule: time at the waypoint runs from the first reading inside the zone to the first reading outside it. That includes the start of the return's climb (about 1.1 s in test flights, `docs/px4-mappings.md` section 5).
- What a gap in the log does to the hold check. `docs/px4-mappings.md` section 5 has a proposal.
- When a log counts as a complete flight, and how the checks combine into one verdict for a run. A log cut off after landing reads as a normal end today (R5 wants INCONCLUSIVE).
- Fixture format (trimmed `.ulg` or extracted traces) and how they're produced. Fixtures come with the "Validate the verifier" work.
- The verifier's language and libraries, command line and report format ("Implement verifier" card).
- Whether testers also stay out of the verifier's code, and who reviews verifier PRs.
- Which simulator the baseline runs use. The sample logs are Gazebo `x500`; quick-setup also runs SIH.
- Whether a mission should test PX4's own geofence. It is off in every flight today (`px4_setup`), so a variant that breaks it would go unnoticed.
- Where the shared helper functions live. `platform_configs/px4.yaml` lists them under `helpers`; none is written yet.
- Whether CI on recorded logs meets the course's Research CI gate ([Repo Checkpoints](https://capstone.alexulbrich.com/assignments/repo-checkpoints/#what-ci-must-do)). To ask the TA.

The verifier plan lays out options for the tolerances, RTL timing and never-lands questions, and lists some of them as questions for Manish. Record a decision that is expensive to reverse (tolerances, the report format, which simulator the baseline uses) in an ADR (`docs/adr/`); record smaller ones in the document that owns them. Either way, remove it from this list.

## Not adopted yet

Mutation testing, property-based testing (Hypothesis), coverage reports, and simulation runs in CI. If we measure coverage, it is for finding untested code and is never a target ([handbook, Testing Strategy](https://capstone.alexulbrich.com/guides/testing-strategy/)).
