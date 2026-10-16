"""Classify a failing log tail with a local model, or a labeled heuristic."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

CLASSES = {"CODE_BUG", "ENV_MISMATCH", "UNVERIFIABLE_LOCALLY", "FLAKY"}
TOKEN_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|npm_[A-Za-z0-9]{20,}|"
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*)"
)
FLAKY_RE = re.compile(r"flaky|econnreset|etimedout|timed out", re.IGNORECASE)
ENV_KINDS = {"node_version", "python_version", "os", "missing_env", "missing_secret", "lockfile"}


def model_name() -> str:
    return os.environ.get("CI_REHEARSAL_MODEL", "qwen2.5-coder:3b")


def redact(text: str) -> str:
    return TOKEN_RE.sub("[REDACTED]", text or "")


def heuristic(log_tail, env_diff, skip_reason) -> dict:
    if skip_reason:
        klass = "UNVERIFIABLE_LOCALLY"
        summary = skip_reason
        fix = "Run this check in GitHub Actions; it cannot be rehearsed locally."
    elif FLAKY_RE.search(log_tail or ""):
        klass = "FLAKY"
        summary = "The log matches a transient failure pattern."
        fix = "Re-run the step. If it fails again, treat it as a code or environment bug."
    elif any(item.get("kind") in ENV_KINDS for item in (env_diff or [])):
        klass = "ENV_MISMATCH"
        summary = "Local environment differs from CI."
        fix = "Align the local runtime, OS, env vars, or lockfile with the workflow."
    else:
        klass = "CODE_BUG"
        summary = "The step failed and no environment mismatch explains it."
        fix = "Read the log tail and fix the failing code or test."
    return {
        "class": klass,
        "summary": summary,
        "suggested_fix": fix,
        "confidence": 0.4,
        "triage_source": "heuristic",
    }


def build_prompt(log_tail, env_diff) -> str:
    return (
        "Classify this CI failure. Reply with JSON keys class, summary, suggested_fix, confidence. "
        "class must be one of CODE_BUG, ENV_MISMATCH, UNVERIFIABLE_LOCALLY, FLAKY.\n"
        f"env_diff: {json.dumps(env_diff or [])}\n"
        f"log:\n{redact(log_tail)}"
    )


def triage_step(log_tail, env_diff, skip_reason=None, complete=None) -> dict:
    fallback = heuristic(log_tail, env_diff, skip_reason)
    if skip_reason:
        return fallback
    prompt = build_prompt(log_tail, env_diff)
    complete = complete or ollama_complete
    try:
        raw = complete(prompt)
    except Exception:
        return fallback
    parsed = _parse_model(raw)
    return parsed or fallback


def _parse_model(payload):
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("class") not in CLASSES:
        return None
    if not data.get("summary") or not data.get("suggested_fix"):
        return None
    return {
        "class": data["class"],
        "summary": str(data["summary"]),
        "suggested_fix": str(data["suggested_fix"]),
        "confidence": float(data.get("confidence") or 0.5),
        "triage_source": "ollama",
    }


def ollama_complete(prompt, base_url=None, timeout=30) -> str:
    base = (base_url or os.environ.get("CI_REHEARSAL_OLLAMA", "http://127.0.0.1:11434")).rstrip("/")
    body = json.dumps(
        {
            "model": model_name(),
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": "You diagnose CI logs. Return only JSON."},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("message", {}).get("content", "")


def triage_results(plan, results, complete=None) -> list:
    env_diff = plan.get("env_diff") or []
    by_id = {step["id"]: step for step in plan.get("steps") or []}
    output = []
    for step in results.get("steps") or []:
        failed = not step.get("skipped") and step.get("exit_code") not in (0, None)
        if not failed:
            continue
        planned = by_id.get(step.get("id"), {})
        item = triage_step(
            step.get("log_tail") or "",
            env_diff,
            planned.get("skip_reason"),
            complete=complete,
        )
        item["step_id"] = step.get("id")
        output.append(item)
    return output


def main():
    parser = argparse.ArgumentParser(description="Classify failing rehearsal steps")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", default="-")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    payload = json.dumps(triage_results(plan, results), indent=2)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
