# ADR 0003: The people testing the verifier don't build it

Status: Accepted. Decided by the team at the planning meeting, 2026-10-20 (project doc, meeting notes), matching the Trello card "Validate the verifier"; reviewed in the PR that adds this record.

## Context

The verifier will reject invalid variants and decide which ones enter the attack-transfer experiment (project doc §11, weeks 7 and 8), so a wrong verdict changes a research result. Someone who builds the verifier and also tests it brings one reading of the spec to both, so their tests can't catch a requirement they misread. The Trello card "Validate the verifier" says the work "should be completed by someone not on the implementation team". As of Oct 22, "Implement verifier" is Brendon's card and "Validate the verifier" is Gabriel's and Luca's.

## Options considered

- **Testers who are not the builders:** chosen.
- **Builders test their own verifier:** rejected, because their cases would encode the same reading of the spec as the code.

## Decision

The people testing the verifier are not the people building it.

## Not decided

- Whether testers also stay out of the verifier's code and work only from the spec, the command, and the report format. The verifier plan suggests it; the team hasn't decided it.
- Who reviews verifier PRs. Brendon is the only builder on the card, and every PR needs an approval from someone other than its author, so a tester may end up reviewing verifier code.

Both are tracked in [`docs/testing.md`](../testing.md#not-decided-yet).

## Consequences

- Testers need the spec, the verifier's command, and its report format to run cases. The command and the report format are not decided yet.
- Expected results come from the spec, never from the verifier's own output ([`docs/testing.md`](../testing.md)), so a mismatch points at a verifier bug or a gap in the spec.
