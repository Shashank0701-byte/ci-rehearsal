"""Parse GitHub Actions workflows into a rehearsal plan."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

import yaml

SECRET_RE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)")
VARS_RE = re.compile(r"\$\{\{\s*vars\.([A-Za-z0-9_]+)")
EXPR_RE = re.compile(r"\$\{\{")
DANGEROUS_SCRIPT = re.compile(
    r"(\bnpm\s+publish\b|\byarn\s+publish\b|\bpnpm\s+publish\b|"
    r"\btwine\s+upload\b|\bdocker\s+push\b|\bgh\s+release\b|"
    r"\bgit\s+push\b|\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\bshutdown\b)",
    re.IGNORECASE,
)
DANGEROUS_NAME = re.compile(r"\b(deploy|release|publish)\b", re.IGNORECASE)
LOCKFILE_CHECKS = (
    ("npm ci", "package-lock.json"),
    ("poetry install", "poetry.lock"),
    ("uv sync", "uv.lock"),
)


def parse_workflows(root, probe=None) -> dict:
    root = Path(root)
    workflow_dir = root / ".github" / "workflows"
    plan = {"jobs": [], "steps": [], "unverifiable": [], "env_diff": []}
    files = []
    if workflow_dir.is_dir():
        files = sorted(set(workflow_dir.glob("*.yml")) | set(workflow_dir.glob("*.yaml")))
    if not files:
        plan["unverifiable"].append(
            {"item": ".github/workflows", "reason": "no workflow files found"}
        )
        return plan

    for path in files:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            plan["unverifiable"].append(
                {"item": path.name, "reason": f"invalid workflow YAML: {exc.__class__.__name__}"}
            )
            continue
        if not isinstance(doc, dict):
            plan["unverifiable"].append(
                {"item": path.name, "reason": "workflow root is not a mapping"}
            )
            continue
        _consume_document(doc, path.name, plan)

    plan["env_diff"] = build_env_diff(plan, local_probe() if probe is None else probe, root)
    return plan


def _workflow_on(doc):
    # PyYAML 1.1 parses the bare key `on` as boolean True.
    if "on" in doc:
        return doc["on"]
    if True in doc:
        return doc[True]
    return None


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _triggers_and_paths(on_block):
    if on_block is None:
        return [], [], []
    if isinstance(on_block, str):
        return [on_block], [], []
    if isinstance(on_block, list):
        return [str(item) for item in on_block], [], []
    if not isinstance(on_block, dict):
        return [], [], []
    events, paths, paths_ignore = [], [], []
    for event, cfg in on_block.items():
        events.append(str(event))
        if isinstance(cfg, dict):
            paths.extend(str(item) for item in _as_list(cfg.get("paths")))
            paths_ignore.extend(str(item) for item in _as_list(cfg.get("paths-ignore")))
    return events, paths, paths_ignore


def _walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value)


def _secrets_in(node):
    found = []
    for text in _walk_strings(node):
        found.extend(SECRET_RE.findall(text))
    return list(dict.fromkeys(found))


def _runs_on(job):
    value = job.get("runs-on", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _runtime(job):
    runtime = {"node": None, "python": None}
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses") or "")
        with_block = step.get("with") if isinstance(step.get("with"), dict) else {}
        if uses.startswith("actions/setup-node"):
            runtime["node"] = str(with_block.get("node-version") or "") or None
        if uses.startswith("actions/setup-python"):
            runtime["python"] = str(with_block.get("python-version") or "") or None
    return runtime


def _dangerous(name, script):
    return bool(DANGEROUS_NAME.search(name or "") or DANGEROUS_SCRIPT.search(script or ""))


def _consume_document(doc, filename, plan):
    events, paths, paths_ignore = _triggers_and_paths(_workflow_on(doc))
    jobs = doc.get("jobs") or {}
    if not isinstance(jobs, dict):
        plan["unverifiable"].append({"item": filename, "reason": "jobs is not a mapping"})
        return
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            plan["unverifiable"].append({"item": str(job_name), "reason": "job is not a mapping"})
            continue
        secrets = _secrets_in(job)
        for secret in secrets:
            plan["unverifiable"].append(
                {"item": secret, "reason": "secrets cannot be verified locally"}
            )
        plan["jobs"].append(
            {
                "name": str(job_name),
                "file": filename,
                "runs_on": _runs_on(job),
                "triggers": events,
                "runtime": _runtime(job),
                "env": job.get("env") if isinstance(job.get("env"), dict) else {},
                "secrets": secrets,
                "paths": paths,
                "paths_ignore": paths_ignore,
            }
        )
        if "uses" in job and "steps" not in job:
            plan["unverifiable"].append(
                {
                    "item": f"{filename}:{job_name}",
                    "reason": "reusable workflows cannot be verified locally",
                }
            )
            continue
        strategy = job.get("strategy")
        matrix_blocked = isinstance(strategy, dict) and bool(strategy.get("matrix"))
        if matrix_blocked:
            plan["unverifiable"].append(
                {
                    "item": f"{filename}:{job_name}",
                    "reason": "matrix builds cannot be verified locally",
                }
            )
        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            plan["steps"].append(_step_record(filename, str(job_name), index, step, matrix_blocked))
            if "uses" in step:
                plan["unverifiable"].append(
                    {
                        "item": str(step.get("uses")),
                        "reason": "third-party actions are not executed locally",
                    }
                )


def _step_record(filename, job_name, index, step, matrix_blocked):
    uses = step.get("uses")
    script = step.get("run") if isinstance(step.get("run"), str) else None
    name = str(step.get("name") or uses or (script or "")[:40] or f"step-{index}")
    if script is not None:
        kind = "run"
    elif uses:
        kind = "uses"
    else:
        kind = "unknown"
    verifiable = kind == "run"
    skip_reason = None
    if matrix_blocked:
        verifiable = False
        skip_reason = "matrix builds cannot be verified locally"
    elif kind == "uses":
        verifiable = False
        skip_reason = f"action {uses} is not executed locally"
    elif kind != "run":
        verifiable = False
        skip_reason = "step has no run script"
    elif _dangerous(name, script or ""):
        verifiable = False
        skip_reason = "deploy, publish, or destructive step is skipped"
    stem = Path(filename).stem
    return {
        "id": f"{stem}-{job_name}-{index}",
        "job": job_name,
        "name": name,
        "kind": kind,
        "script": script,
        "verifiable": verifiable,
        "skip_reason": skip_reason,
        "timeout_sec": 120,
    }


def _os_family_ci(runs_on: str) -> str:
    text = runs_on.lower()
    if "ubuntu" in text or "linux" in text:
        return "linux"
    if "windows" in text:
        return "windows"
    if "macos" in text:
        return "macos"
    return "unknown"


def _os_family_local(system: str) -> str:
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(system, "unknown")


def _major(version: str):
    match = re.search(r"(\d+)", version or "")
    return match.group(1) if match else None


def _major_minor(version: str):
    match = re.search(r"(\d+)\.(\d+)", version or "")
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return _major(version)


def build_env_diff(plan, probe, root: Path):
    diff = []
    seen = set()

    def add(kind, expected, actual, detail):
        key = (kind, str(expected), str(actual), detail)
        if key in seen:
            return
        seen.add(key)
        diff.append(
            {"kind": kind, "expected": str(expected), "actual": str(actual), "detail": detail}
        )

    for job in plan["jobs"]:
        runs_on = job["runs_on"]
        if EXPR_RE.search(runs_on):
            add("os", runs_on, probe.get("system", ""), "runs-on is an expression and cannot be compared")
        else:
            ci_os = _os_family_ci(runs_on)
            local_os = _os_family_local(probe.get("system", ""))
            if ci_os != "unknown" and ci_os != local_os:
                add("os", runs_on, probe.get("system", ""), f"CI runs on {ci_os}, local machine is {local_os}")

        _compare_runtime(add, "node_version", job["runtime"].get("node"), probe.get("node") or "", _major, "node major differs", "node is not installed locally")
        _compare_runtime(add, "python_version", job["runtime"].get("python"), probe.get("python") or "", _major_minor, "python version differs", "python is not installed locally")

        local_env = probe.get("env") or {}
        for key, value in (job.get("env") or {}).items():
            text = str(value)
            secrets = SECRET_RE.findall(text)
            if secrets:
                add("missing_secret", secrets[0], "", f"{key} references a secret")
                continue
            if VARS_RE.search(text) and key not in local_env:
                add("missing_env", key, "", f"{key} is not set locally")

    scripts = "\n".join(step.get("script") or "" for step in plan["steps"])
    for command, filename in LOCKFILE_CHECKS:
        if command in scripts and not (Path(root) / filename).exists():
            add("lockfile", filename, "missing", f"{command} requires {filename}")
    return diff


def _compare_runtime(add, kind, expected, actual, picker, differ_detail, missing_detail):
    if not expected:
        return
    if EXPR_RE.search(expected):
        add(kind, expected, actual, f"{kind} is an expression")
        return
    wanted = picker(expected)
    found = picker(actual)
    if wanted and found and wanted != found:
        add(kind, expected, actual, differ_detail)
    elif wanted and not found:
        add(kind, expected, "", missing_detail)


def local_probe():
    def version(cmd):
        if shutil.which(cmd[0]) is None:
            return ""
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return (completed.stdout or completed.stderr or "").strip()

    python = version(["python", "--version"])
    return {
        "node": version(["node", "-v"]),
        "python": python.split()[-1] if python else "",
        "system": platform.system(),
        "env": dict(os.environ),
    }


def main():
    parser = argparse.ArgumentParser(description="Parse GitHub Actions workflows into a rehearsal plan")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="-")
    args = parser.parse_args()
    plan = parse_workflows(args.root)
    payload = json.dumps(plan, indent=2)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
