"""Render a deterministic rehearsal report. The model does not write this."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def verdict(plan, results, triages) -> str:
    failures = _failures(results)
    if failures:
        return "likely red"
    if plan.get("unverifiable") or plan.get("env_diff"):
        return "incomplete"
    return "likely green"


def render_report(plan, results, triages) -> str:
    by_id = {item.get("step_id"): item for item in triages or []}
    lines = [f"Verdict: {verdict(plan, results, triages)}", "", "Environment mismatches"]
    diffs = plan.get("env_diff") or []
    if not diffs:
        lines.append("- none")
    else:
        for item in diffs:
            lines.append(f"- {item.get('detail') or item.get('kind')}")
    lines.extend(["", "Failures"])
    failures = _failures(results)
    if not failures:
        lines.append("- none")
    for step in failures:
        triage = by_id.get(step.get("id"), {})
        lines.append(
            f"- {step.get('name')} (exit {step.get('exit_code')}) {triage.get('class', 'CODE_BUG')}"
        )
        if triage.get("summary"):
            lines.append(f"  {triage['summary']}")
        if triage.get("suggested_fix"):
            lines.append(f"  suggested fix: {triage['suggested_fix']}")
        source = triage.get("triage_source")
        if source:
            lines.append(f"  source: {source}")
    lines.extend(["", "Not verified"])
    unverifiable = plan.get("unverifiable") or []
    if not unverifiable:
        lines.append("- none")
    else:
        for item in unverifiable:
            lines.append(f"- {item.get('item')}: {item.get('reason')}")
    lines.append("")
    return "\n".join(lines)


def _failures(results):
    return [
        step
        for step in (results.get("steps") or [])
        if not step.get("skipped") and step.get("exit_code") not in (0, None)
    ]


def main():
    parser = argparse.ArgumentParser(description="Render a ci-rehearsal report")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--triage", required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    triages = json.loads(Path(args.triage).read_text(encoding="utf-8"))
    print(render_report(plan, results, triages), end="")


if __name__ == "__main__":
    main()
