# Design

The system view someone needs to contribute safely. Reasons for decisions live in [`docs/adr/`](adr/); this file links them where they apply.

## Context

What the system is, and what it takes in and hands on.
Source: project doc §2, §4 and §5.

TODO(team)

## Key diagrams

The pipeline (mission spec → PX4 SITL → `.ulg` flight log → verifier → report) and its parts.
Source: project doc §2.

TODO(team)

## Interfaces and contracts

The verifier's inputs (`.plan` and `.ulg`), its command, and its report format.
Source: verifier plan, "Starting suggestions"; [ADR 0003](adr/0003-independent-verifier-validation.md).

TODO(team)

## Data model

The mission spec, the log topics and fields the checks use, and the result per requirement.
Source: project doc §6; verifier plan, "Starting suggestions" and "What our flights show".

TODO(team)

## Deployment

Repo Checkpoint 1 needs one paragraph here: where the walking skeleton runs in week 10, who owns the account or infrastructure, and who agreed it.
Source: handbook, Repo Checkpoint 1; project doc §11 (week 10).

TODO(team): agree with Manish.

## Deferred decisions

Decisions put off on purpose, with when each will be made.
Source: [`docs/testing.md`](testing.md#not-decided-yet), the one tracked list of open decisions; [ADR 0002](adr/0002-verify-from-logs.md) (live checking).

TODO(team)

## Open technical questions

Questions to answer with a spike or a test flight.
Source: [`docs/testing.md`](testing.md#not-decided-yet), the one tracked list of open decisions; verifier plan, "Two open questions" and "Open questions for Manish".

TODO(team)
