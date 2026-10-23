# Contributing Guide

How we set up, check, review, and merge changes to HYDRA (formerly DASA) so every change meets our Definition of Done. Team roles, decisions, and conflict are in our team charter; this file covers the repository. Rules for AI coding agents are in [`AGENTS.md`](AGENTS.md).

## Code of conduct

Be respectful and critique code, not people. We follow the OSU Student Code of Conduct. Report problems to the Project Manager (Brendon Wong), or to the instruction team if the PM is involved.

## Development setup

Start with the [README quickstart](README.md#quickstart). Beyond it:

- Python 3.12 or newer. CI runs 3.12. On Windows, work inside WSL2 Ubuntu.
- Dev dependencies (pytest and ruff) are pinned to exact versions in [`requirements-dev.txt`](requirements-dev.txt) and installed into `.venv`. Tool settings are in [`pyproject.toml`](pyproject.toml). There is no lock file yet.
- Adding or upgrading a dependency is ask-first (see `AGENTS.md`) and goes in its own `chore/` PR.
- No environment variables, secrets, or local services are needed yet. A PR that adds one documents it here, with how to get its value, and commits only a `.env.example`.
- The checks below don't need PX4. Flying missions does: install it with quick-setup as [ADR 0001](docs/adr/0001-dev-environment.md) describes.

## Local checks

Run these from the repo root (inside WSL2 Ubuntu on Windows). They are the same ones CI runs.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check . && pytest     # the full check, same as CI
ruff format .                                      # fix formatting
```

| CI job | Runs |
|---|---|
| `test` | `pytest` |
| `lint` | `ruff check .` and `ruff format --check .` |

Both jobs are in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and run on every pull request. Results and re-runs are in the PR's Checks tab. A check that keeps failing for no clear reason goes to the Quality Owner. Style isn't debated in review: if ruff accepts it, it's fine.

Test conventions are in [`docs/testing.md`](docs/testing.md): pytest tests in `tests/`, small fixtures in `tests/fixtures/`, how to run part of the suite, placeholders for undecided values, and how a flaky test is quarantined.

## Branches and commits

- The default branch is `main`. It always works, and every change reaches it through a pull request.
- Branch from the latest `main`. Name the branch with a prefix (`feature/`, `fix/`, `docs/`, `exp/`, or `chore/`) and a short slug. Example: `feature/altitude-check`.
- Branches are short-lived.
- Commit subjects are short and imperative (about 50 characters), with a body when the reason isn't obvious. Example: `Add altitude tolerance check to verifier`. Reference issues with `Fixes #12`.
- A PR lands on `main` as one squashed commit titled with the PR title (or with the commit's subject if the PR has one commit), so PR titles follow the same style.

## Pull requests and review

- Use the [PR template](.github/pull_request_template.md). Link the Trello card, paste the commands you ran with their output, and keep the PR small enough to review in one sitting. A small chore with no card (a dependency bump, a typo fix) writes "no card" instead; anything with a decision in it gets a card.
- A teammate other than the author approves. One approval is required. Nobody self-merges.
- Reviews arrive within one business day and ask for specific changes. "LGTM" alone doesn't count as a review in sprint notes.
- Copilot code review is requested automatically when a PR opens. It is advisory and never replaces a teammate's approval. Its comments are fixed or answered like anyone else's.
- Before a PR merges, every review thread is resolved (Copilot's included), the `test` and `lint` checks pass, and the branch is up to date with `main`. A new push dismisses earlier approvals, so ask for a fresh review after pushing.
- PRs merge by squash only, and the branch is deleted on merge.
- Docs change in the same PR as the code they describe.
- The author owns everything in the PR, including AI-written code, and must be able to explain it. Structural changes suggested by an AI tool go through an ADR first.

## Definition of Done

A change merges only when it passes every check below. `main-protection` is the ruleset on `main`.

| Check | Enforced by | Status |
|---|---|---|
| Reaches `main` through a PR approved by a teammate other than the author | `main-protection`: PR required, 1 approval, empty bypass list | On |
| The approval covers the latest push | `main-protection`: stale approvals dismissed on new pushes | On |
| All review threads resolved, including Copilot's | `main-protection`: thread resolution required, Copilot review requested automatically | On |
| Tests pass | `test` job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml), a required status check in `main-protection` | Pending: the check becomes required once the workflow has run on `main` (owner: Gabriel) |
| Lint and format clean | `lint` job in the same workflow, a required status check in `main-protection` | Pending, same as above |
| Branch up to date with `main` | `main-protection`: strict status checks | Pending, set together with the required checks |
| Squash merge, linear history, no force-push to or deletion of `main` | `main-protection` and the repo's merge settings | On |
| New or changed logic has tests. Verifier changes have PASS, FAIL, and INCONCLUSIVE cases ([`docs/testing.md`](docs/testing.md)) | PR template checklist, checked by the reviewer | On |
| Docs updated when behavior or setup changes | PR template checklist, checked by the reviewer | On |
| No secrets committed | GitHub secret scanning and push protection | On while the repo is public. When it goes private, a gitleaks CI job replaces them (owner: Gabriel) |
| An experiment can be rerun by a teammate with the same result | A run record in the PR (commit, PX4 version, simulator and airframe, parameters, mission, seed, and the model and prompt for generated variants). PR template checklist, checked by the reviewer | On for experiment PRs |

## Where other work lives

| Work | Lives in | Accepted by |
|---|---|---|
| Tasks and other non-repository work, each with an owner, an expected outcome, and a due date | Trello board "DASA Capstone" | The team: the outcome is written on the card and the card moves to Done at a Friday meeting |
| Bugs and setup problems | GitHub Issues | TODO(Brendon) |
| The project plan and meeting notes | The project Google Doc | TODO(Brendon) |
| Decisions that constrain code | `docs/adr/`, through a PR | A teammate other than the author, as for any PR |
| The RFC | The repo, under `docs/rfcs/` or `docs/adr/` (handbook) | A teammate other than the author, as for any PR |
| Team documents: the charter, sprint notes, and retrospectives | The team's shared Drive folder, not the repo (handbook) | The charter: every teammate, before it is submitted (handbook). TODO(Brendon): sprint notes and retrospectives |

Links and access for each are in [`docs/sources.md`](docs/sources.md). Cards are sized to finish in two or three days; bigger ones get split.

## Contribution norm

Each of us lands at least one piece of accepted work per sprint: a merged PR (code, docs, ADRs, literature notes, or an experiment with its run record) or a Trello card accepted as above. Formatter runs, dependency bumps, and generated files don't count on their own. To keep this workable, we review within one business day, pair on setup-heavy work, and post in Teams when blocked for more than a day.

## Security and secrets

- No credentials, API keys, or `.env` files in the repository.
- Report a leaked secret or vulnerability privately to the Quality Owner, not in an issue or PR. A leaked key gets revoked, not just deleted.
- What may go into AI tools follows the AI and Confidentiality section of the charter and `AGENTS.md`.
- Attack and failure experiments run only inside the simulation environment.

## Release process

There is no release yet. At the end of each term the Quality Owner tags `main` (for example `fall-2026`) after the checks and a manual smoke run pass. A fuller process is set before Winter week 1 (owner: Gabriel Simek).

## Getting help

Ask in the DASA Teams chat. If nobody answers within 3 to 5 hours, ping again. Email gets a reply within 24 hours.

- Tasks and the board: Brendon Wong (Project Manager)
- AI tools and what can be shared: Luca Regazzoni (AI Coordinator)
- CI, tests, reviews, and this file: Gabriel Simek (Quality Owner)
