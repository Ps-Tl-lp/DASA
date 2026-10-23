# ADR 0002: Verify missions from recorded flight logs

Status: Accepted. Decided by the team with Manish Motwani at the planning meeting, 2026-10-20 (project doc, meeting notes); reviewed in the PR that adds this record.

## Context

The verifier decides whether a flight met its mission requirements. The evidence can come from the recorded `.ulg` flight log after the flight, or from live telemetry during it. Project doc §6 names `.ulg` logs as the preferred execution record for PX4. Live checking can stop a failed run early, but stopping early loses information about the rest of the run.

## Options considered

- **Recorded `.ulg` logs, with every check run:** chosen.
- **Live (streamed) checking that bails out on the first failure:** rejected for now, because it loses evidence the remaining checks need. Manish suggested logs might be combined with live checking later.

## Decision

The verifier judges recorded `.ulg` flight logs, not live telemetry. Every check runs on every log; no check is skipped because another one failed.

## Consequences

- A report has a result for every requirement, even for a failed flight.
- The verifier's input is a file, so its tests can run on recorded logs without a simulator.
- A failed run is only judged after its log is complete.
- Live checking may be revisited later. That needs a new ADR.
