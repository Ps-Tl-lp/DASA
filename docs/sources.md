# Sources outside the repo

The repo is the source of record for decisions that constrain code (`docs/adr/`). The plan, tasks, meeting notes, and environment setup live in the sources below. Agents usually can't open the team-only ones, so ask a teammate for the excerpt you need.

## Priority

An accepted ADR wins for what it decides (each ADR cites its source). Otherwise: project doc > Trello card > verifier plan > other repo docs. On a conflict, follow the higher source and flag it in the PR.

## Sources

| Source | Link | What's there | Who can open it |
|---|---|---|---|
| Project plan and meeting notes | [Google Doc](https://docs.google.com/document/d/1IO4phoOHADkrAYb4e316cDlXaGPaYNOdbFkqVuHxyJw/edit) | The team's single source of truth (Oct 13 meeting). Goal §1, red and blue workstreams §4, verifier checks §6, repo structure §8, weekly milestones §11. Meeting notes at the end, newest first. | Team Google accounts |
| Verifier plan (draft, Oct 22) | [Google Doc](https://docs.google.com/document/d/1xhm-_O4FKUWdXvWfAV6_XaXU9NsUcIitvYouGffeArI/edit) | Tolerances, roles, validation cases, risks, and open questions for the verifier. Starting suggestions, not decisions. | Team Google accounts |
| Trello board "DASA Capstone" | [Board](https://trello.com/b/CrvpRogM/dasa-capstone) | Tasks, owners, and expected outcomes. The `class` label marks course tasks. Verifier cards: [Create an approach](https://trello.com/c/6CMuoiok), [Implement verifier](https://trello.com/c/sw3CdhwJ), [Validate the verifier](https://trello.com/c/beYmLDIM). | Board members |
| quick-setup | [dasa-capstone/quick-setup](https://github.com/dasa-capstone/quick-setup) | The PX4 environment install ([ADR 0001](adr/0001-dev-environment.md)) | dasa-capstone org members |
| ulog-extract-demo | [dasa-capstone/ulog-extract-demo](https://github.com/dasa-capstone/ulog-extract-demo) | A proof of concept for reading `.ulg` logs, not the verifier. Only `extract/to_json.py` and the README's Gotchas matter. | dasa-capstone org members |
| Shared Drive folder "DASA Capstone Files" | TODO(Gabriel): add link | Team files and class deliverables. Raw baseline `.ulg` logs will go here. | Team Google accounts |
| Testing and CI research notes (Oct 22) | TODO(Gabriel): add link once uploaded to the shared Drive | Course requirements, tools, and open questions about testing the verifier. Background, not decisions. | Team Google accounts |
| CS Capstone handbook | [capstone.alexulbrich.com](https://capstone.alexulbrich.com/) | Course expectations, such as Repo Checkpoints and the Testing Strategy guide | Public |
| PX4 guide, v1.18 | [docs.px4.io/v1.18](https://docs.px4.io/v1.18/en/index.html) | PX4 docs for our version line. v1.18 isn't PX4's stable release yet, and the guide can differ from rc1 in details. | Public |

## What not to do

- Don't paste meeting notes or doc exports into the repo. Copies drift from the source.
- A decision that constrains code becomes an ADR in `docs/adr/` that cites its source.
- Don't commit credentials for these services, and don't add a shared connector config for them.
