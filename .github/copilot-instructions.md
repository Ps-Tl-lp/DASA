# Copilot review instructions

Project context and rules are in `AGENTS.md` and `CONTRIBUTING.md`. When reviewing pull requests, focus on:

- Verifier logic: PASS only with adequate evidence of satisfaction, FAIL only with adequate evidence of a violation, INCONCLUSIVE when evidence is missing or invalid. Flag anything that passes by default or hides errors.
- Missing tests for new logic, especially FAIL and INCONCLUSIVE cases.
- Tests whose expected values were copied from the verifier's own output instead of coming from the spec.
- Tests edited, skipped, or deleted to make the suite pass. A flaky-test skip needs a linked issue, as `docs/testing.md` describes.
- Unseeded randomness and experiments without a run record.
- Inconsistent units or hard-coded tolerances.
- Secrets, keys, `.env` contents, or anything resembling partner data.

Skip formatting and minor naming comments. Keep comments short, and mark optional ones "nit:".
