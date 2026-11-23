# Requirements
 
What HYDRA must do and how we will know. Updated as scope changes; git history is the change log.
 
## Goal
 
The research question and what the project must show.
Source: project doc §1 and §10.
 
**Research question:** Can AI-generated software diversity reduce attack transferability while preserving required mission behavior? The question may be refined as we study related work and finish the first experiments (§1).
 
**Why it matters:** Autonomous systems often run identical software across many vehicles. That monoculture means an attack found against one implementation may transfer to every other one. HYDRA tests whether AI-assisted diversification produces implementations that (1) still complete the mission, (2) differ meaningfully from each other, and (3) make an attack developed against one less likely to work on the others.
 
**By the end of Fall the project should show (§10):**
 
1. A reproducible PX4 simulation environment.
2. The three existing missions (simple, medium, survey) running reliably.
3. An automated mission verifier.
4. A clearly defined baseline autonomous-software configuration.
5. At least one controlled failure/attack scenario.
6. At least one software-diversification approach.
7. At least one generated or transformed variant that still passes mission verification.
8. A preliminary experiment testing whether the failure/attack transfers between the baseline and a valid variant.
## Requirements and acceptance criteria
 
Current priorities, each with a criterion a teammate can mark passed or failed.
Source: project doc §6 and §11 (week 3); the Trello cards for the current week.
 
### Fall plan by week
 
Every Fall milestone from §11, starting at week 1. Update **Status** at each Friday progress check. When the plan itself changes, add a dated line under [Changes to the plan](#changes-to-the-plan).
 
Status values: **Done** · **In progress** · **Not started** · **To confirm**. *To confirm* means the work probably happened but the meeting notes don't show that it meets the criterion.
 
| Week | Deliverable | Acceptance criterion | Status |
|------|-------------|----------------------|--------|
| 1 | Repository and board active; existing materials organized | The GitHub repo and Trello board are in use. Prithvi's code, docs, mission files, and references are in the repo. Setup problems are filed as GitHub issues. | Done (repo, board) · To confirm (materials, issues) |
| 1 | Repo cleanup | The repo is private and named HYDRA. Each person has one account. No AI reviewers appear as contributors. Profiles are reviewed. | To confirm |
| 1 | Baseline simulation reproducible | A teammate who didn't write the setup docs follows them and completes the simple mission on their own machine. | To confirm |
| 2 | Three baseline missions reproducible | Simple, medium, and survey each run. For every run, the mission file, software versions, simulator settings, parameter snapshot, run ID, flight log and simulator recording are preserved. A documented run procedure lets someone else repeat it. | To confirm |
| 3 | First mission verifier | R1–R9 below pass, ending in an automated verification report for the three baseline missions. | In progress |
| 4 | Red/Blue literature study | Each workstream presents 3–5 feasible options (Red: attack/failure categories; Blue: diversification strategies) and recommends a first experiment. | Not started |
| 5 | Initial experimental target | A written Experiment 1 design names the component or behavior to diversify (not all of PX4), the first attack/failure scenario, the mission-success criteria, and the evidence to collect. GitHub issues are assigned. | Not started |
| 6 | First reproducible failure + first variants | Red: one failure scenario reproduces against the baseline, documented with its assumption, trigger, expected failure, reproducibility, and configuration (§4). Blue: a diversification pipeline produces candidate variants. | Not started |
| 7 | First valid diversified variant | At least one variant compiles, runs, and passes mission verification. The verifier rejects invalid variants. | Not started |
| 8 | First attack-transfer experiment | The same failure/attack runs against the baseline and every valid variant. Verification results, attack outcomes, and execution data are recorded, and the Attack Transfer Rate is computed. | Not started |
| 9 | Diversity metrics | Several diversity measures are implemented (e.g. token, AST, CFG, execution trace, trajectory), with a table or plot comparing diversity to observed transfer. | Not started |
| 10 | Fall evaluation and Winter plan | A short internal Fall report (what worked, what failed, technical challenges, new research questions, Winter experiments) and a working end-to-end demo. | Not started |
 
### Week 3 detail: mission verifier
 
The current priority is the mission verifier. Per the Oct 30 decision, the high-level approach is settled before verifier code is written, so R1–R2 come first.
 
#### Approach (due before Tue Nov 3)
 
| ID | Requirement | Acceptance criterion |
|----|-------------|----------------------|
| R1 | Every mission is represented as R = {precondition, start state, goal state, postcondition}, following the five-step verification approach. Each mission has one goal state. Start and goal states are full snapshots of the environment. Pre- and postconditions are specific to the mission. | Each team member can write one of the three baseline missions in this form, as in Manish's photo example. The written forms are in `docs/` and Manish has reviewed them. |
| R2 | Mappings are explicit: every log parameter or recorded value the verifier uses is mapped to the part of the goal state it gives evidence for, with a one-line reason. | A reader outside the team can trace every decision to the log fields it uses from the docs alone. No mapping exists only in code or in someone's head. |
 
#### Verifier
 
| ID | Requirement | Acceptance criterion |
|----|-------------|----------------------|
| R3 | The verifier works only with the general mission representation. Platform-specific details reach it through the mappings. | Decision code contains no ULog field names. Supporting a new platform means adding mappings, not changing decision code. |
| R4 | The verifier maps log parameters and recorded values to the goal state and decides whether the mission was accomplished (step 5). | For each of the three baseline missions, the report says whether the final state matched the goal state and whether the pre- and postconditions held. |
| R5 | Every decision is PASS, FAIL, or INCONCLUSIVE, with a reason. Missing or invalid evidence gives INCONCLUSIVE, never PASS. | A truncated or corrupted log, or a log that disagrees with the simulator's recording, produces INCONCLUSIVE, not PASS. Every verdict includes a reason (e.g. "goal state not reached: no picture taken at b"). |
| R6 | Mission-completion tolerances are chosen on runs of the unmodified autopilot, each with a reason. | No tolerance value is hard-coded in decision code. Each tolerance has a reason and names the reference runs it was tuned on. |
| R7 | The verifier runs on logs and recordings after the flight and does not stop at the first failure. | A run that fails partway still produces a full report. |
| R8 | A mission only counts if the unmodified autopilot passes it on reference runs. | Each mission in the suite has recorded passing reference runs of the baseline; any that fail are listed as excluded with a reason. |
| R9 | The verifier is validated by people who did not build it. | The validation report is written by teammates other than the verifier's authors. |
 
### Changes to the plan
 
Dated changes to scope or approach, newest last. Add a line whenever a meeting moves the plan.
 
- **Oct 23:** Verifier reframed from checking PX4 waypoints to checking a general mission definition (start state, goals, constraints). Waypoints become one case of a goal.
- **Oct 28:** Team proposed a declarative mapping spec (`.plan` → definition, expected outcome → ULog fields, with a reason per entry). Pending Manish's confirmation.
- **Oct 29:** QGroundControl dropped from the loop as unnecessary complexity.
- **Oct 30:** The five-step approach and the mission representation R = {precondition, start state, goal state, postcondition} replace §6's seven checks and draft v11's definition. Each mission has one goal state, start and goal states are full environment snapshots, and pre- and postconditions are specific to the mission. The approach is settled before verifier code. Automated mission generation becomes step 2 of the approach, earlier than §12's Winter plan for random missions.
## Constraints
 
Limits we did not choose, such as the platform, course rules, and partner rules.
Source: project doc §2 and §8; [ADR 0001](adr/0001-dev-environment.md).
 
**Platform**
- PX4 is the primary platform, run as software-in-the-loop (SITL) simulation (§2).
- The development environment follows [ADR 0001](adr/0001-dev-environment.md) and is set up with [quick setup](https://github.com/dasa-capstone/quick-setup). Like the ADR, this leaves the simulator and airframe open.
- Execution evidence is the PX4 flight log (`.ulg`) and the harness's recording of the simulator's pose of the vehicle, made outside PX4 (§6). Position, velocity and landed come from the recording, and the log's own copy is cross-checked against it. The flight mode, arming state, disarm reason and camera trigger come from the log. (Changed 2026-11-23 with the PX4 config's call 3, for the team to approve: a modified autopilot could change its own log.)
- PX4 is an evaluation platform only. The verifier design and variant generation must stay general and not depend on PX4 (Oct 13, Oct 30).
**Safety and scope**
- All attack and failure experiments stay inside the project simulation/test environment (§4).
**Partner rules (Manish)**
- Agree on the high-level approach as a team before implementing (Oct 20, Oct 30).
- Use LLMs, but understand what they produce. Research and design thinking are not handed to AI (Oct 20).
- Cite relevant literature before major technical choices; record unsuccessful approaches as well as successful ones (§9).
- Decisions and contributions must be documented and attributable (Oct 23).
**Repository and process**
- One shared GitHub repository and one project board (§8).
- Workflow: Issue → Branch → Implementation → Pull Request → Review → Merge (§8).
- Every significant task has an owner, expected outcome, and completion criteria (§8).
- Major decisions and experimental results are recorded in GitHub, not only in chat or meetings (§8, Oct 30).
- The repo is private and named HYDRA. One GitHub account per person; AI reviewers do not appear as contributors (Oct 23).
**Team and schedule**
- Three capstone students plus one undergraduate researcher. Red and Blue are workstreams, not fixed teams, and roles may rotate (§3, §4).
- Fall, Winter, and Spring terms, with the Fall goals in §10.
- Course rules: see the [capstone handbook](https://capstone.alexulbrich.com).
## Non-goals
 
What the project won't do, so nobody builds it.
Source: project doc §4 and §12.
 
**Project-wide**
- No attacks or failure testing outside the simulation/test environment (§4).
- Red work is not about simply crashing the system. It looks for reproducible scenarios that expose a specific assumption or weakness (§4).
- No diversifying the whole PX4 codebase. We pick a manageable component or behavior (§11 week 5).
- Variants don't need identical trajectories, only the same mission-level requirements (§4).
- No ArduPilot until the core PX4 study is stable; that is a Spring consideration (§12).
- No randomly generated missions until the fixed missions are reliable (Winter, §12).
- No large-scale empirical evaluation or statistical analysis in Fall; that is Spring work (§12).
**Verifier**
- Separate pass/fail checks for each of §6's seven items. Since Oct 30, the verifier compares the run against the mission's goal state instead (step 5).
- Live, in-flight checking ([ADR 0002](adr/0002-verify-from-logs.md); logs only for now, Oct 20).
## Success metrics
 
How we measure the research outcome.
Source: project doc §5 and §10.
 
**Primary metric**
- **Attack Transfer Rate (ATR)** = other variants affected ÷ other variants tested (§5). An attack or failure scenario that succeeds against one implementation is run against the other valid variants. The hypothesis is that diversified variants show a lower ATR.
**Diversity measures (§5, §11 week 9)**
- Several notions of diversity are measured: source-code/token similarity, AST/structural, control-flow (CFG), algorithmic, execution-trace, and trajectory/behavioral.
- The eventual research question is whether greater measured diversity is associated with lower ATR. The first output is a comparison table or plot of diversity against observed transfer.
**Validity gate**
- Only variants that pass mission verification count in ATR (§5, §11 week 7). The share of generated variants that pass is worth tracking alongside ATR.
**Fall progress**
- The eight Fall goals listed under [Goal](#goal) (§10), ending in a preliminary transfer experiment between the baseline and at least one valid variant.
Negative results (e.g. attacks that transfer regardless of diversity) count as research findings (§9).
 
## Open product questions
 
Questions that change scope, each with who answers it.
Source: [`docs/testing.md`](testing.md#not-decided-yet), the one tracked list of open decisions; verifier plan, "Decisions for the team" and "Open questions for Manish".
 
| # | Question | Who answers |
|---|----------|-------------|
| Q1 | Confirm the five-step approach and representation as written here, and the mapping approach (Oct 28 proposal), including where tolerances live. | Manish (Brendon raises it) |
| Q2 | ATR: how do INCONCLUSIVE results count? Does a slower but still successful run count as the attack succeeding? | Manish |
| Q3 | Can a mapping include small transforms (unit conversions, coordinate frames, reducing a time series to a final value), or only direct field reads? | Team, then Manish |
| Q4 | What are the tolerance values for the current platform setup? (Action item from Oct 20; tuned on reference runs per R6.) | Team |
| Q5 | With one goal state per mission, how do the medium and survey missions show that several waypoints were visited? Manish's example records a visit as part of the state (the picture at b). | Team, then Manish |
 