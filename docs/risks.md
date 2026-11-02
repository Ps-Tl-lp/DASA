# Risks
 
The project's one risk register, ranked. Each risk is written as a fact about the project, without blame.
 
## Ranked risks
 
Technical, schedule, and team-process risks together, highest first.
Source: verifier plan, "Risks"; project doc §11.
 
| Rank | Risk | Likelihood | Impact |
|---|---|---|---|
| 1 | **Schedule slip.** The week 3 deliverable, the mission verifier, is still at the approach stage in week 5. Weeks 4–10 (literature study, Experiment 1, variants, transfer experiment, metrics) are compressed into the remaining Fall weeks, and the §10 Fall goals may not all be met. | High | High |
| 2 | **Communication gaps.** Decisions are spread across several meetings, chats, and Google Docs. Not everyone is at every meeting, meeting notes aren't always signed off, and on Oct 27 the team noted it wasn't on the same page. Work can be duplicated, or built on a decision someone missed. | High | High |
| 3 | **Unsettled approach.** The five-step approach and the mission representation R = {precondition, start state, goal state, postcondition} were set on Oct 30, but the details are still being settled and the log-to-goal-state mappings aren't written up yet. Code built on them now may need reworking. | High | Medium |
| 4 | **Unsettled verdict rules for transfer.** It isn't decided how INCONCLUSIVE runs count in the Attack Transfer Rate, or whether a slower but successful run counts as the attack succeeding. Week 8 results could be ambiguous or have to be redone. | Medium | High |
| 5 | **Missing-evidence detection.** The ground-truth `*_valid` flags are never set in the logs recorded so far, so the verifier has no built-in signal for bad position data. A gap or corrupt log could be judged PASS instead of INCONCLUSIVE. | Medium | High |
| 6 | **Tolerances not chosen.** Mission-completion thresholds (action item from Oct 20) are still open. Loose values accept broken variants; tight values reject valid ones. Either way the transfer rate is skewed. | Medium | High |
| 7 | **Diversification scope.** LLM-generated variants of PX4 code may not compile, may not pass verification, or may barely differ from the baseline. That puts the week 7 deliverable (one valid variant) at risk. | Medium | High |
| 8 | **Environment reproducibility.** The development environment in [ADR 0001](adr/0001-dev-environment.md) has been tested on two platforms. Other machines or a PX4 update may behave differently. | Medium | Medium |
| 9 | **SITL run-to-run variation.** Repeated runs of the same mission may not be identical. Baseline missions can then fail the feasibility rule, and attack-transfer results become noisy. | Medium | Medium |
| 10 | **Implicit mappings.** Some mappings from log fields to the mission exist only in code or in people's heads. Manish flagged this on Oct 30, and outside readers and graders can't follow them. | Medium | Medium |
| 11 | **AI use and attribution.** AI tools help write code and notes. Manish asked that the team understand everything it uses and keep research thinking human, and noted that AI reviewers and multiple accounts made the contributor graph hard to read. | Medium | Medium |
| 12 | **Low measured diversity.** Variants may turn out too similar for transfer to drop, giving a near-100% transfer rate. | Medium | Low |
 
## External prerequisites
 
Approvals, accounts, and reviews we need from outside the team.
 
| Prerequisite | Needed for | Who is asking | Asked of | When asked |
|---|---|---|---|---|
| GitHub Team plan for the dasa-capstone org | Enforcing branch rules and secret scanning on the private repo | The team | Manish (GitHub Education for teachers) | In progress, not yet asked |
| Read access to the repo for the TA and instructors | Grading Repo Checkpoints on the private repo | The team | The TA and instructors | Granted |
| Partner agreement on the week 10 production target | The production target in docs/design.md (Deployment) | The team | Manish | Not yet asked; Nov 3 partner meeting |