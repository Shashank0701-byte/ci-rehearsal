# PRD: ci-rehearsal

**An agent skill that rehearses your CI pipeline locally before you push, learns from your repo's past CI failures, and uses a local open-weight model to diagnose what broke.**

- **Author:** Shashank Chakraborty
- **Target:** Hacktoberfest 2026, "Best Open-Source AI Project" (MLH / DEV)
- **Status:** Draft v0.1
- **Deadline:** Oct 31, 2026 (about 15 days from Oct 16)
- **License:** MIT

---

## 1. Problem

The common loop: write code, push, wait for CI, CI fails, read the logs, fix, push again. Each round trip costs 3-10 minutes plus the context switch. It also clutters the commit history with "fix lint" and "fix ci" commits.

Existing tools only half solve it:

| Tool | What it does | What's missing |
|---|---|---|
| `act` | Runs GitHub Actions locally | Doesn't tell you *why* something failed or whether local results can be trusted |
| pre-commit / husky hooks | Run fixed checks | Hand-maintained, drift away from the real workflow, know nothing about your CI history |
| Pasting the log into an AI chat | Explains one failure | Manual, sends private code and logs to a third party, no memory of past failures |

The real gap is not "run the pipeline locally". It is **knowing what in local differs from CI, running the likeliest failures first, and being honest about what can't be verified locally.**

## 2. Product vision

Before every push, the agent runs `ci-rehearsal`. In under a minute it answers one question: **"If I push this now, will CI go green, and if not, why?"**

It is not another pipeline runner. It is a trust layer on top of one.

## 3. Goals and non-goals

### Goals
1. Catch the majority of avoidable CI failures (lint, type check, unit tests, build, version mismatches) before the push.
2. Be honest: clearly separate "verified locally" from "cannot verify locally".
3. Get smarter per repo by mining that repo's own CI failure history.
4. Keep code and logs on the user's machine by default (local open-weight model for log triage).
5. Comply fully with the Agent Skills open standard and work across agent clients (Claude Code, Codex, Cursor, Gemini CLI, etc.).
6. Ship with evals that show the skill measurably helps, including on small open-weight models.

### Non-goals (v1)
- CI systems other than GitHub Actions (GitLab CI, Jenkins, CircleCI come later).
- Docker-in-Docker, service containers, matrix builds, self-hosted runners.
- Deploy, release, and publish steps (these are flagged "cannot verify", never run).
- Auto-pushing. The skill never pushes.
- Languages beyond Node/TypeScript and Python in v1.

## 4. Target users

- **Primary:** students and solo developers on GitHub who push often and get bitten by CI.
- **Secondary:** small teams with a GitHub Actions workflow and slow CI queues.
- **Persona:** "I know my code works, why is CI red again?"

## 5. User flow

```
User: "I'm about to push" / "rehearse CI" / agent is about to run `git push`
        |
        v
[1] PARSE      parse_workflows.py reads .github/workflows/*.yml
        |      -> triggers, jobs, steps, env, secrets, runtime versions, path filters
        v
[2] SCOPE      diff changed files vs path filters -> which jobs would actually trigger
        |
        v
[3] ENV CHECK  compare local vs CI: Node/Python version, OS, env vars, secrets, lockfile
        |      -> report mismatches BEFORE running anything
        v
[4] PRIORITIZE history.json (mined from past failed runs) -> run historically-flaky/failing steps first
        |
        v
[5] RUN        run_steps.sh executes steps in order, collects ALL failures (no fail-fast), timeouts per step
        |
        v
[6] TRIAGE     triage.py sends only the failing log tail to a local open-weight model (Ollama)
        |      -> classify: CODE_BUG | ENV_MISMATCH | UNVERIFIABLE_LOCALLY | FLAKY
        v
[7] REPORT     verdict + per-failure cause + suggested fix + "not verified" list
        |
        v
[8] FIX LOOP   (optional, capped at N attempts) agent applies fix, re-runs only failed steps
        |
        v
User decides to push. The skill never pushes.
```

## 6. Features

### P0 (must ship)
| ID | Feature | Detail |
|---|---|---|
| F1 | Workflow parser | Deterministic script. Extracts jobs, `run:` steps, `uses:` actions, `env`, `secrets.*` references, `runs-on`, runtime versions (`setup-node`, `setup-python`), and `paths` / `paths-ignore` filters |
| F2 | Local/CI environment diff | Flags version, OS, missing env var, and missing secret mismatches before running |
| F3 | Step runner | Runs the extracted `run:` steps in order, per-step timeout, collects all failures, structured JSON output |
| F4 | Failure classification | Four classes: `CODE_BUG`, `ENV_MISMATCH`, `UNVERIFIABLE_LOCALLY`, `FLAKY` |
| F5 | Honest report | Always lists what was NOT verified (secrets, deploy steps, unsupported actions) |
| F6 | Local open-weight triage | Failing log tail goes to a local model via Ollama; no network call required |
| F7 | Eval harness | Real failed-CI logs, with-skill vs without-skill, small vs large model, scored table in README |

### P1 (ship if time allows)
| ID | Feature | Detail |
|---|---|---|
| F8 | History miner | `gh run list --status failure` + `gh run view --log-failed` -> `history.json` of failure patterns per repo; reorders steps by failure likelihood |
| F9 | Diff-aware scoping | Only run jobs whose path filters match the changed files |
| F10 | Capped fix loop | Apply a fix, re-run only the failed steps, stop after N attempts |
| F11 | `act` integration | Optional: use `act` for steps that need the Actions runtime when it's installed |

### P2 (post-hackathon)
GitLab CI support, matrix builds, caching of step results, git `pre-push` hook installer, team-shared history.

## 7. Architecture

### Repo structure (Agent Skills-compliant)

```
ci-rehearsal/                  <- directory name MUST equal `name` in frontmatter
├── SKILL.md                   # frontmatter + short instructions (<500 lines, ideally <5000 tokens)
├── scripts/
│   ├── parse_workflows.py     # F1, F2, F9
│   ├── run_steps.sh           # F3
│   ├── triage.py              # F4, F6 (Ollama client + prompt + JSON schema)
│   └── mine_history.py        # F8
├── references/
│   ├── failure-patterns.md    # loaded only when diagnosing
│   └── env-mismatch-guide.md  # loaded only on ENV_MISMATCH
├── evals/
│   ├── logs/                  # real failed CI logs + expected cause labels
│   ├── run_evals.py
│   └── RESULTS.md             # generated results table
├── README.md
├── PRD.md
└── LICENSE                    # MIT
```

### Design principles
- **Deterministic where it must be exact, LLM where judgment is needed.** Parsing, env diffing, and running are scripts. Only log triage and fix suggestions use a model.
- **Progressive disclosure.** Description is sharp so it triggers at the right moment, SKILL.md stays short, detail lives in `references/` (one level deep).
- **Agent-agnostic.** Scripts have no dependency on any one agent client. They emit JSON the agent reads.
- **Fail honest.** Unknown action or unsupported step means "cannot verify", never a silent skip.

### Spec compliance checklist (agentskills.io)
- [ ] `name`: lowercase, hyphens only, max 64 chars, equals the directory name (`ci-rehearsal`)
- [ ] `description`: required, max 1024 chars, says what it does AND when to use it
- [ ] SKILL.md body under 500 lines; file references one level deep
- [ ] Optional fields used correctly (`license`, `compatibility` for Python/Ollama/gh requirements)
- [ ] `skills-ref validate ./ci-rehearsal` passes
- [ ] Tested in at least two clients (e.g. Claude Code and Codex)

### Draft frontmatter

```yaml
---
name: ci-rehearsal
description: Rehearses the project's GitHub Actions CI locally before a push. Finds local-vs-CI environment mismatches, runs the likeliest-to-fail steps first, diagnoses failures with a local open-weight model, and reports what could not be verified. Use when the user is about to push, asks "will CI pass", wants to avoid a red build, or after a CI failure.
license: MIT
compatibility: Requires git, Python 3.10+, and a GitHub Actions workflow. Optional - Ollama for local triage, gh CLI for history mining, act for Actions runtime.
---
```

## 8. Open-weight AI: why it is central, not decorative

The challenge requires open-source / open-weight AI to be an important part of how the project works. In `ci-rehearsal`:

1. **Triage runs on a local open-weight model by default** (e.g. a small Qwen or Llama via Ollama). CI logs routinely contain private code, paths, and tokens. Keeping triage local is a real product feature, not a checkbox.
2. **The eval measures the skill's effect on small open models.** The headline result we want: "with the skill, a small local model diagnoses CI failures correctly X% of the time vs Y% without".
3. **Model is swappable** through one config value, so users with better hardware or a hosted model can switch.

Risk: if the open-weight step feels bolted on, judges will notice. Mitigation: triage is on the critical path of every failure report, and the eval centers on it.

## 9. Evaluation plan

- **Corpus:** 15-20 real failed CI logs from public GitHub repos (Node and Python), each hand-labeled with the true cause class and root cause.
- **Conditions:** (a) model alone, (b) model + skill (structured prompt, classification schema, env diff context). Run on at least two model sizes (one small open-weight, one larger).
- **Metrics:**
  - Cause-class accuracy (4 classes)
  - Root-cause correctness (human-judged yes/no)
  - Hallucinated-fix rate (suggested fix that doesn't apply)
  - Time to verdict
- **Output:** `evals/RESULTS.md` table, reproduced in README.
- **Honesty rule:** publish the results even if the skill only helps on some conditions.

## 10. Success metrics

**For the hackathon**
- Public repo, MIT license, passes `skills-ref validate`
- Works end-to-end on at least 3 real repos (including the author's own)
- Eval table showing a measurable improvement
- A 60-90 second demo: push would have failed, skill catches it, explains why, fix applied

**For real usage**
- % of "would have failed" pushes caught locally
- Reduction in "fix ci" follow-up commits on the author's repos
- Stars and installs after the DEV post

## 11. Timeline (Oct 16 to Oct 31)

| Days | Milestone |
|---|---|
| Oct 16-17 | Repo scaffold, SKILL.md draft, `parse_workflows.py` (F1) |
| Oct 18-19 | Env diff (F2), step runner (F3) |
| Oct 20-22 | Triage with Ollama (F4, F6), report format (F5) |
| Oct 23-25 | Collect and label eval logs, eval harness (F7) |
| Oct 26-27 | P1: history miner (F8), diff-aware scoping (F9) |
| Oct 28-29 | Cross-client testing, spec validation, bug fixes |
| Oct 30 | README, demo recording, DEV post |
| Oct 31 | Submit (buffer day, do not plan to use it) |

If the schedule slips, cut in this order: F11, F10, F9, then F8. Never cut F5 (honest report), F6 (open-weight triage), or F7 (evals).

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Looks like a wrapper around `act` | Seen as unoriginal | Position as a trust layer: env diff, history mining, honest report, local triage. `act` is optional |
| Workflow YAML edge cases (reusable workflows, composite actions) | Parser breaks | Unsupported constructs become "cannot verify", never crash or skip silently |
| Small model triages badly | Weak eval story | Constrain output with a JSON schema and a classification prompt; report real numbers either way |
| Local run passes but CI fails anyway | Loss of trust | The "not verified" list is mandatory in every report |
| Scope creep | Misses deadline | P0 only until Oct 25; cut order defined above |
| Running arbitrary workflow `run:` steps locally is risky | Could run destructive commands | Show the step list first, skip deploy/publish/`rm -rf`-style steps by default, require confirmation for anything outside an allowlist |
| Logs contain secrets | Leakage | Local-only triage by default; redact obvious token patterns before any non-local model call |

## 13. Submission checklist (Hacktoberfest 2026 rules)

- [ ] Public GitHub repository
- [ ] OSI-approved open-source license (MIT)
- [ ] Skill complies with the Agent Skills open standard
- [ ] Open-weight AI is an important part of how it works (local triage + evals)
- [ ] Original implementation
- [ ] README with install steps, demo GIF, and eval results
- [ ] DEV post describing the project

## 14. Open questions

1. Which small open-weight model is the default (Qwen, Llama, Gemma, other)? Decide after the first eval pass.
2. Should the skill install a git `pre-push` hook, or stay purely agent-invoked? (Leaning: agent-invoked for v1.)
3. Ship `mine_history.py` in v1 or hold for v1.1? (Leaning: ship if the P0 work is done by Oct 25.)
