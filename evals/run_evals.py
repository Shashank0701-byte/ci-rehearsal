"""Score cause-class accuracy with and without rehearsal context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from triage import heuristic, ollama_complete, triage_step

LOGS = Path(__file__).resolve().parent / "logs"


def load_cases(logs_dir=LOGS):
    logs_dir = Path(logs_dir)
    cases = []
    for label_path in sorted(logs_dir.glob("*.label.json")):
        label = json.loads(label_path.read_text(encoding="utf-8"))
        stem = label_path.name[: -len(".label.json")]
        label["log"] = (logs_dir / f"{stem}.log").read_text(encoding="utf-8")
        cases.append(label)
    return cases


def predict_bare(case) -> str:
    return heuristic(case["log"], [], None)["class"]


def predict_with_context(case) -> str:
    return heuristic(case["log"], case.get("env_diff") or [], case.get("skip_reason"))["class"]


def score(cases, predict) -> dict:
    correct = sum(1 for case in cases if predict(case) == case["class"])
    total = len(cases)
    accuracy = (correct / total) if total else 0.0
    return {"correct": correct, "total": total, "accuracy": accuracy}


def model_available() -> bool:
    try:
        ollama_complete("Reply with JSON.", timeout=3)
    except Exception:
        return False
    return True


def render_results(rows) -> str:
    lines = [
        "# Eval results",
        "",
        "Cause-class accuracy. Bare conditions see only the log tail. Skill conditions also see the rehearsal env diff and skip reason.",
        "",
        "| Condition | Model | Correct | Total | Accuracy | Note |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        accuracy = f"{row['accuracy']:.0%}" if row["total"] else "n/a"
        lines.append(
            f"| {row['condition']} | {row['model']} | {row['correct']} | {row['total']} | {accuracy} | {row.get('note', '')} |"
        )
    lines.extend(
        [
            "",
            "Root-cause correctness and hallucinated-fix rate are human-judged and left blank until reviewed.",
            "",
            "| Condition | Root-cause correctness | Hallucinated-fix rate |",
            "|---|---|---|",
            "| bare |  |  |",
            "| skill |  |  |",
            "",
        ]
    )
    return "\n".join(lines)


def build_rows(cases, probe_model=False) -> list:
    bare = score(cases, predict_bare)
    skill = score(cases, predict_with_context)
    rows = [
        {"condition": "bare heuristic", "model": "none", **bare, "note": "log tail only"},
        {"condition": "skill heuristic", "model": "none", **skill, "note": "log plus env diff and skip reason"},
    ]
    if not probe_model or not model_available():
        rows.append(
            {
                "condition": "bare model",
                "model": "ollama",
                "correct": 0,
                "total": 0,
                "accuracy": 0,
                "note": "skipped; Ollama not reachable",
            }
        )
        rows.append(
            {
                "condition": "skill model",
                "model": "ollama",
                "correct": 0,
                "total": 0,
                "accuracy": 0,
                "note": "skipped; Ollama not reachable",
            }
        )
        return rows

    def bare_model(case):
        return triage_step(case["log"], [], None)["class"]

    def skill_model(case):
        return triage_step(case["log"], case.get("env_diff") or [], case.get("skip_reason"))["class"]

    bare_row = score(cases, bare_model)
    skill_row = score(cases, skill_model)
    rows.append({"condition": "bare model", "model": "ollama", **bare_row, "note": "model sees the log only"})
    rows.append({"condition": "skill model", "model": "ollama", **skill_row, "note": "model sees log plus env diff"})
    return rows


def main():
    parser = argparse.ArgumentParser(description="Run ci-rehearsal cause-class evals")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "RESULTS.md"))
    parser.add_argument("--probe-model", action="store_true")
    args = parser.parse_args()
    text = render_results(build_rows(load_cases(), probe_model=args.probe_model))
    Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
