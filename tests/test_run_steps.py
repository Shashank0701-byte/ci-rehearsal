import pytest

from run_steps import ConfirmationRequired, run_steps


def test_refuses_without_confirmation():
    with pytest.raises(ConfirmationRequired):
        run_steps({"steps": []}, confirmed=False)


def test_collects_every_failure(tmp_path):
    plan = {
        "steps": [
            {"id": "a", "name": "a", "kind": "run", "script": "python -c \"import sys; sys.exit(1)\"", "verifiable": True, "skip_reason": None, "timeout_sec": 30},
            {"id": "b", "name": "b", "kind": "run", "script": "python -c \"import sys; sys.exit(2)\"", "verifiable": True, "skip_reason": None, "timeout_sec": 30},
        ]
    }
    results = run_steps(plan, confirmed=True, cwd=tmp_path)
    codes = {step["id"]: step["exit_code"] for step in results["steps"]}
    assert codes == {"a": 1, "b": 2}


def test_does_not_run_skipped_steps(tmp_path):
    plan = {
        "steps": [
            {
                "id": "deploy",
                "name": "Deploy",
                "kind": "run",
                "script": "python -c \"open('ran.txt','w').write('x')\"",
                "verifiable": False,
                "skip_reason": "deploy, publish, or destructive step is skipped",
                "timeout_sec": 30,
            }
        ]
    }
    results = run_steps(plan, confirmed=True, cwd=tmp_path)
    assert results["steps"][0]["skipped"] is True
    assert not (tmp_path / "ran.txt").exists()


def test_timeout_is_recorded(tmp_path):
    plan = {
        "steps": [
            {
                "id": "slow",
                "name": "slow",
                "kind": "run",
                "script": "python -c \"import time; time.sleep(30)\"",
                "verifiable": True,
                "skip_reason": None,
                "timeout_sec": 1,
            }
        ]
    }
    results = run_steps(plan, confirmed=True, cwd=tmp_path)
    assert results["steps"][0]["exit_code"] != 0
    assert "timeout" in results["steps"][0]["log_tail"].lower()
