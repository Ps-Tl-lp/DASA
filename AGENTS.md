# AGENTS.md

Context for AI coding agents working in this repository. A line belongs here only if removing it would cause a mistake. People should read `README.md` and `CONTRIBUTING.md`.

## Project

HYDRA (formerly DASA) is a research project on whether AI-generated software diversity reduces attack transferability while preserving required mission behavior. We use PX4 flight software in simulation.

- **Pipeline:** mission spec (QGroundControl `.plan`) → PX4 SITL → `.ulg` flight log → verifier → PASS / FAIL / INCONCLUSIVE per requirement.
- **Workstreams:** Red builds controlled failure and attack scenarios. Blue generates diversified variants that must still pass the verifier.
- **Docs:**
  - Requirements: `docs/requirements.md`
  - Design: `docs/design.md`
  - Decisions and their reasons: `docs/adr/`
  - Testing: `docs/testing.md`
  - Sources outside the repo: `docs/sources.md`
  - Mission plans: `missions/`
  - Risks: `docs/risks.md`. If a task touches a risk or raises a new one, say so in the PR, but don't edit the file.
- **Definition of Done and review rules:** `CONTRIBUTING.md`

## Commands

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check . && pytest     # the full check, same as CI
ruff format .                                      # fix formatting
```

Flying missions needs PX4: see ADR 0001 (quick-setup), `docs/adr/0001-dev-environment.md`.

## Work

- Tasks are Trello cards. Each PR links its card in the description, except the small chores `CONTRIBUTING.md` exempts.
- A task is done when the card's expected outcome and the Definition of Done in `CONTRIBUTING.md` are both met.
- Work on a short-lived branch, named as `CONTRIBUTING.md` says, and open a PR. Never commit to `main`.

## Conventions

- Layout: `missions/`, `tests/`, and `docs/` exist. Planned: `verifier/`, `diversification/`, `attacks/`, `experiments/`, `scripts/`, `results/`.
- The verifier returns PASS only with adequate evidence of satisfaction, FAIL only with adequate evidence of a violation, and INCONCLUSIVE when evidence is missing or invalid. It never passes by default. Every check runs, with no early bail-out (ADR 0002).
- Tolerances and units are never hard-coded in check logic; where they are defined is not decided.
- Seed all randomness. Every experiment writes a run record: commit, PX4 version, simulator and airframe, parameters, mission, seed, and the model and prompt for generated variants.
- Small test fixtures go in `tests/fixtures/`. Raw flight logs and run output stay out of git.
- The people testing the verifier are not the people building it (ADR 0003). Expected values in tests never come from the verifier's own output (`docs/testing.md`).
- Open decisions are listed in [`docs/testing.md#not-decided-yet`](docs/testing.md#not-decided-yet). Don't pick one silently: leave a `PLACEHOLDER:` comment that names it, and list it in the PR.

## Sources outside the repo

`docs/sources.md` lists the project doc, the Trello board, and the other outside sources, who can open each, and which source wins on a conflict. If a task depends on a source you can't open, ask for the excerpt instead of guessing.

## Boundaries

**Always**
- Run the full check before calling a task done, and put its output in the PR.
- Keep changes to the scope of the linked card.
- Say what you're unsure about rather than guessing.

**Ask first**
- Adding or upgrading dependencies.
- Changing the PX4 version, simulator setup, or mission definitions.
- Changing verifier pass/fail criteria or tolerances.
- Editing CI workflows, repo settings, or anything partner-facing.
- Structural changes. These need an ADR in `docs/adr/` before code.

**Never**
- Commit to `main`, force-push, or skip review.
- Edit, skip, or delete tests to make them pass. A flaky test is quarantined only as `docs/testing.md` describes, with an Issue.
- Put credentials, `.env` contents, partner data, unpublished results, or meeting recordings into any prompt, external tool, or commit.
- Run attack or failure-injection code anywhere except the local simulation.
- Commit large files or raw flight logs.

## Confidentiality

What may go into which AI tools is set by the AI and Confidentiality section of the team charter. That section is being confirmed with our project partner. Until it is, treat Prithvi's existing code, experiment results, and meeting content as restricted: use them only in tools the team has approved. Public PX4 docs, generic code, and error messages with paths and keys removed are fine anywhere.

## To be added

| What | Owner | When |
|---|---|---|
| Module map, the verifier's commands, and the conventions the code doesn't make obvious | Luca | When the verifier lands |
| Simulator pitfalls from reproducing the baseline missions that quick-setup's docs don't cover | Brendon | TODO(Brendon): set a date |
| Rules for generating LLM variants (approved API and model, where prompts are stored, cost limits) | Luca | After the partner confirms approved tools |
| Shared agent skills committed to the repo | Luca | TODO(Luca): set a date |
