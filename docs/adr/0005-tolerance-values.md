# ADR 0005: How tolerance values are set

Status: Proposed in the PR that adds this record. Decided by Gabriel on 2026-11-23, for the team to approve in review.

## Context

`platform_configs/px4.yaml` holds the tolerances (ADR 0004). Each was marked PROPOSED with one or two flights behind it, and the file mixed two kinds of number:
- **Requirements** say what the mission counts as done, such as "at the waypoint".
- **Noise allowances** absorb how much correct flights of the unmodified PX4 vary, such as how much shorter than the hold a stretch may read.

Getting the method wrong costs something either way:
- Setting a requirement from measured noise would let the mission's meaning drift with the simulator.
- Setting a noise allowance by hand hides how much margin it has.

PX4's own test tolerances carry no written basis either.

## Options considered

- **Each value set by hand, with the evidence in a comment:** what we had. Nothing says when a value may change, or what a change needs.
- **Every value from baseline runs:** this ties "at the waypoint" to whatever the simulator does, so a sloppier simulator would quietly loosen the mission.
- **Requirements chosen; noise allowances from baseline runs, by a fixed method:** proposed.

## Decision

- **Every tolerance's comment** says which kind it is. `docs/px4-mappings.md` section 5 says which flights, PX4 builds and sim speed are behind it.
- **A requirement** is chosen as part of what the mission means. Section 5 gives the measured error as the margin. Changing one is a research decision with its own PR: a tighter value catches smaller drift in a variant.
- **A noise allowance** is set, and changed, only from a baseline: at least 10 complete runs of the unmodified PX4 per mission and setup (simulator, speed, PX4 build).
  - The value is the larger of 3σ and the widest variation seen, rounded up.
  - If the widest variation in a baseline reaches half the current allowance, investigate before using the baseline.
- **Where the numbers live:** `docs/px4-mappings.md` section 5 keeps them, with the run count, build and speed behind each.
- **Precedent:** RVFuzzer sets its bounds at 3σ over 31 runs, and Houston rejects a baseline whose runs spread too far.

## Consequences

- **The current values stand, provisionally** (2026-11-23). They predate this method.
  - No mission and build pair has 10 baseline runs yet.
  - `log_gap_max_s` trips the investigate rule: one 0.136 s gap was seen, more than half of 0.2 s.
  - The first 10-run baseline per setup is a follow-up. Until then section 5 gives the runs each value has.
  - Requirements: `at_waypoint` and `at_goal`.
  - Noise allowances: `hold_short_by_s`, `log_gap_max_s`, `geofence_clearance_m`, `landed`, `cross_check_m` and `cross_check_time_s`.
- **A new setup needs its own baseline.** Runs on another simulator, speed or PX4 build aren't judged with these allowances until then. The evidence so far is from Gazebo at 4x, on fca3df865a and 6d1773f4c1.
- **"Tolerance values" leaves "Not decided yet"** in `docs/testing.md`.
