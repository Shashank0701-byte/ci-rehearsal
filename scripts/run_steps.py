"""Run verifiable workflow steps and collect every failure."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


class ConfirmationRequired(RuntimeError):
    """Raised when the runner is asked to execute steps without a yes."""


def detect_shell():
    """Pick a shell that can see this machine's tools.

    Windows prefers PowerShell. Git Bash is present on most Windows dev
    machines but does not inherit the Windows Python path, so CI `run:`
    steps would fail before the project did. Linux and macOS use bash.
    """
    if os.name == "nt":
        order = (("powershell", ["-NoProfile", "-Command"]), ("pwsh", ["-NoProfile", "-Command"]), ("bash", ["-c"]), ("sh", ["-c"]))
    else:
        order = (("bash", ["-c"]), ("sh", ["-c"]))
    for name, args in order:
        path = shutil.which(name)
        if path:
            return [path, *args]
    return None


def run_steps(plan, confirmed=False, cwd=None) -> dict:
    if not confirmed:
        raise ConfirmationRequired("refusing to run steps without confirmation")
    root = Path(cwd or ".")
    results = []
    for step in plan.get("steps") or []:
        if not step.get("verifiable"):
            results.append(
                {
                    "id": step.get("id"),
                    "name": step.get("name"),
                    "exit_code": None,
                    "duration_sec": 0,
                    "log_tail": "",
                    "skipped": True,
                    "skip_reason": step.get("skip_reason"),
                }
            )
            continue
        results.append(_execute(step, root))
    return {"steps": results}


def _execute(step, cwd: Path) -> dict:
    shell = detect_shell()
    script = step.get("script") or ""
    timeout = int(step.get("timeout_sec") or 120)
    start = time.perf_counter()
    if shell is None:
        output = "no local shell found"
        code = 127
    else:
        proc = subprocess.Popen(
            _command(shell, script),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            output = f"{stdout or ''}{stderr or ''}"
            code = proc.returncode
        except subprocess.TimeoutExpired:
            _kill(proc)
            stdout, stderr = proc.communicate()
            output = f"{_text(stdout)}{_text(stderr)}\ntimeout"
            code = 124
    return {
        "id": step.get("id"),
        "name": step.get("name"),
        "exit_code": code,
        "duration_sec": round(time.perf_counter() - start, 3),
        "log_tail": _tail(output),
        "skipped": False,
        "skip_reason": None,
    }


def _kill(proc):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            text=True,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _command(shell, script):
    executable = Path(shell[0]).name.lower()
    if "powershell" in executable or "pwsh" in executable:
        # PowerShell's process exit code collapses native codes unless asked.
        return [*shell, f"{script}; exit $LASTEXITCODE"]
    return [*shell, script]


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _tail(text: str, limit: int = 80) -> str:
    return "\n".join((text or "").splitlines()[-limit:])


def main():
    parser = argparse.ArgumentParser(description="Run verifiable steps from a rehearsal plan")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--out", default="-")
    parser.add_argument("--cwd", default=".")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    try:
        results = run_steps(plan, confirmed=args.confirm, cwd=args.cwd)
    except ConfirmationRequired as exc:
        raise SystemExit(str(exc)) from exc
    payload = json.dumps(results, indent=2)
    if args.out == "-":
        print(payload)
    else:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
