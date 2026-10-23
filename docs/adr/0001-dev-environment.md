# ADR 0001: Install environments with quick-setup, PX4 pinned to v1.18.0-rc1

Status: Accepted. Decided by the Quality Owner (Gabriel Simek), 2026-10-22, "until further notice"; reviewed in the PR that adds this record.

## Context

- The project compares flights: baselines, diversified variants, and attacks against each. Log fields and flight behavior can change between PX4 commits, so results only compare if everyone flies the same commit.
- The team works on mixed operating systems.
- Prithvi's earlier environment, as the project doc lists it, is PX4 `v1.18.0-beta1-221-g51e1f5dde7` with the stock `gz_x500` airframe, Gazebo 8.14.0, and QGroundControl Daily v5.1.0, on Windows with Ubuntu 24.04 under WSL.
- The team's sample logs of the simple, medium, and survey missions were flown with `dasa-capstone/quick-setup`, in Gazebo with the `x500` airframe. All three report PX4 commit `fca3df865af36124a28c9d607e850f111dbaaea9` (v1.18.0-rc1).
- The repository's own checks (the mission-plan tests now, verifier tests later) are Python and don't need PX4.

## Options considered

- **quick-setup** (`dasa-capstone/quick-setup`): scripts that install PX4 at a pinned commit, a simulator, and QGroundControl on macOS and on Ubuntu, including WSL2. Chosen.
- **A shared Docker container:** tabled on 2026-10-22, when Docker and containers were put out of scope for now. Revisit if setups drift between machines or a platform can't run quick-setup.
- **Prithvi's original setup instructions:** rejected. The project doc lists that environment as PX4 `v1.18.0-beta1-221-g51e1f5dde7`, not the commit our sample logs came from, on one platform (Windows with Ubuntu 24.04 under WSL).

## Decision

We will install development environments with `dasa-capstone/quick-setup` until further notice.

- PX4 is pinned to commit `fca3df865af36124a28c9d607e850f111dbaaea9` (v1.18.0-rc1), the commit the team's sample logs report.
- Tested platforms: macOS on Apple Silicon, and Windows 11 with WSL2 and Ubuntu 26.04. Ubuntu 24.04 (native or WSL2) is scripted but untested.
- quick-setup runs PX4 with SIH (`./launch.sh sih`) or Gazebo (`./launch.sh gz`), and installs QGroundControl. Which simulator and airframe baseline runs use is not decided ([`docs/testing.md`](../testing.md#not-decided-yet)).
- The repository's own tooling is Python 3.12 or newer with pytest and ruff. Exact versions are pinned in [`requirements-dev.txt`](../../requirements-dev.txt). There is no lock file yet.

## Consequences

- Good: everyone flies the same PX4 commit, so logs from different machines compare.
- Changing the PX4 commit is ask-first ([`AGENTS.md`](../../AGENTS.md)) and needs a new ADR that supersedes this one.
- quick-setup is a private repo, so a contributor needs access to the `dasa-capstone` org before installing PX4.
- Test fixtures, and any SITL run added to CI later, must come from this commit.
- Bad: logs from Prithvi's earlier environment (`v1.18.0-beta1-221-g51e1f5dde7`) may not compare with logs from this commit.
- Bad: v1.18.0-rc1 is a release candidate. PX4's stable docs are for v1.17, so some docs may not match what we fly.
- Bad: Ubuntu 24.04 is untested. Setup problems there, as anywhere, go in a GitHub Issue.

## Confirmation

Every `.ulg` records the PX4 commit in its `ver_sw` info field, which `ulog_info flight.ulg` prints. `ulog_info` isn't in `requirements-dev.txt`; quick-setup installs it, and its [`docs/FLIGHT-LOGS.md`](https://github.com/dasa-capstone/quick-setup/blob/main/docs/FLIGHT-LOGS.md) says where. A fixture or run record from another commit doesn't follow this decision.
