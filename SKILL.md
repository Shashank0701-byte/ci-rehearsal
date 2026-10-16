---
name: ci-rehearsal
description: Rehearses the project's GitHub Actions CI locally before a push. Finds local-vs-CI environment mismatches, runs the likeliest-to-fail steps first, diagnoses failures with a local open-weight model, and reports what could not be verified. Use when the user is about to push, asks "will CI pass", wants to avoid a red build, or after a CI failure.
license: MIT
compatibility: Requires git, Python 3.10+, and a GitHub Actions workflow. Optional - Ollama for local triage, gh CLI for history mining, act for Actions runtime.
---

# CI Rehearsal

Answer one question before a push: if this goes to GitHub Actions now, will CI go green, and if not, why?

The scripts are deterministic. A local open-weight model is used only to classify a failing log tail. This skill never pushes.

## Procedure

Run these from the repository root. Read each JSON file before the next command.

1. Parse workflows and write the plan.

```bash
python scripts/parse_workflows.py --root . --out rehearsal-plan.json
```

2. Show the user every step where `verifiable` is true, every `env_diff` entry, and every `unverifiable` entry. Stop and wait for an explicit yes. Do not run steps without that yes.

3. Run only the confirmed plan.

```bash
python scripts/run_steps.py --plan rehearsal-plan.json --confirm --out results.json
```

4. Classify failures. If Ollama is not running, the script still returns a result and sets `triage_source` to `heuristic`. Say that out loud.

```bash
python scripts/triage.py --plan rehearsal-plan.json --results results.json --out triage.json
```

5. Print the report and give that text to the user.

```bash
python scripts/report.py --plan rehearsal-plan.json --results results.json --triage triage.json
```

6. The user decides whether to push. Do not push, commit, or amend as part of this skill.

## How to read the verdict

- `likely green` means every verifiable step passed, the environment diff is empty, and nothing was skipped.
- `likely red` means a step that actually ran failed.
- `incomplete` means the local run passed or never ran, and something CI checks could not be rehearsed. Do not tell the user CI will pass.

## References

Load these only when they apply. Do not load both up front.

- A failure needs a cause class: read [references/failure-patterns.md](references/failure-patterns.md).
- A class or env diff is `ENV_MISMATCH`: read [references/env-mismatch-guide.md](references/env-mismatch-guide.md).

## Safety

- Never execute a step with `verifiable: false`. Deploy, publish, release, `git push`, `rm -rf`, and `shutdown` are in that set.
- Never invent secret values. Secret names may appear in the report. Values must not.
- Token-shaped strings are redacted before a model call. The default model is local Ollama (`CI_REHEARSAL_MODEL`, default `qwen2.5-coder:3b`). Do not send logs to a hosted model unless the user asks.
- Matrix jobs, reusable workflows, and `uses:` actions are unverifiable in v1. Say so. Do not pretend they ran.
- There is no fix loop in v1. Suggest the fix from triage and stop.
