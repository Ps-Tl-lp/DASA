# ADR 0004: Platform-specific values live in one config file per platform

Status: Proposed in the PR that adds this record. It came up at the team meeting on 2026-11-21, where Gabriel proposed keeping preconditions and tolerances in the PX4 YAML. Nobody objected, and it was not put to the team as a decision.

## Context

The generator, plan step, harness, log reader and verifier all need facts about the platform: which vehicles exist, what a mission has to satisfy to be flyable, how a task becomes a plan item, which log fields to read, and the tolerances for judging them. `docs/testing.md` lists where tolerances are defined as not decided. Requirement R6 says no tolerance value is hard-coded in decision code.

## Options considered

- **One config file per platform, read by every step:** proposed.
- **Preconditions and tolerances inside each mission file:** not proposed. They describe the platform, not one mission.
- **Constants inside each program:** ruled out by R6.

## Decision

Proposed: preconditions, task-to-plan mappings, log readings and tolerances for PX4 live in `platform_configs/px4.yaml`. Another platform gets its own file in the same folder. Programs read these values from the file by name.

## Consequences

- `platform_configs/` is a new top-level folder.
- If accepted, where tolerances are defined is settled. Their values are not: anything marked `PROPOSED` in the file still needs a decision and stays on the list in `docs/testing.md`.
- Another platform needs its own config, plus its own plan writer and log reader if its plan or log format differs.
