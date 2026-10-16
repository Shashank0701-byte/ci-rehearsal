# ci-rehearsal

Rehearse a GitHub Actions workflow on your machine before you push. The skill parses the workflow, reports where your machine differs from CI, runs the steps it can run safely, and classifies failures with a local open-weight model. It never pushes.

Parsing, the environment diff, the step runner, and the final report are deterministic scripts. The model only classifies a failing log tail. If Ollama is not running, classification falls back to a labeled heuristic.

## Install

```bash
pip install -r requirements.txt
```

Optional, for local triage:

```bash
ollama pull qwen2.5-coder:3b
```

Override the model with `CI_REHEARSAL_MODEL`. The default is `qwen2.5-coder:3b`.

## Use

From the repository you are about to push:

```bash
python scripts/parse_workflows.py --root . --out rehearsal-plan.json
python scripts/run_steps.py --plan rehearsal-plan.json --confirm --out results.json
python scripts/triage.py --plan rehearsal-plan.json --results results.json --out triage.json
python scripts/report.py --plan rehearsal-plan.json --results results.json --triage triage.json
```

Read the plan before you pass `--confirm`. Deploy, publish, `git push`, and destructive steps are skipped. Secrets are named in the report and never printed.

Verdicts:

- `likely green` — every verifiable step passed and nothing was left unchecked
- `likely red` — a step that ran failed
- `incomplete` — something CI will do could not be rehearsed, or the local OS / runtime / lockfile does not match

An agent client loads [SKILL.md](SKILL.md). The same scripts run from any client.

## Tests

```bash
python -m pytest
```

## Evals

The corpus is 16 hand-labeled failure tails in [evals/logs](evals/logs). Bare classification sees the log only. Skill classification also sees the environment diff and skip reason a rehearsal would have produced.

```bash
python evals/run_evals.py --probe-model
```

Latest numbers are in [evals/RESULTS.md](evals/RESULTS.md). Model rows stay skipped until Ollama answers. Root-cause correctness and hallucinated-fix rate are blank until a person reviews them.

## Scope

v1 covers GitHub Actions `run:` steps for Node and Python. Matrix jobs, reusable workflows, service containers, and third-party actions are reported as not verified. History mining and path-filter scoping are not in this build.

## License

MIT
