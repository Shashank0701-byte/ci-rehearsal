from report import render_report, verdict


def _plan(unverifiable=None, env_diff=None):
    return {"unverifiable": unverifiable or [], "env_diff": env_diff or [], "steps": []}


def test_green_only_when_nothing_is_open():
    results = {"steps": [{"id": "a", "exit_code": 0, "skipped": False, "name": "unit", "log_tail": ""}]}
    assert verdict(_plan(), results, []) == "likely green"


def test_passed_run_with_unverifiable_items_is_incomplete():
    results = {"steps": [{"id": "a", "exit_code": 0, "skipped": False, "name": "unit", "log_tail": ""}]}
    plan = _plan(unverifiable=[{"item": "NPM_TOKEN", "reason": "secret"}])
    assert verdict(plan, results, []) == "incomplete"


def test_failure_is_likely_red():
    results = {"steps": [{"id": "a", "exit_code": 1, "skipped": False, "name": "unit", "log_tail": "SyntaxError"}]}
    triages = [{"step_id": "a", "class": "CODE_BUG", "summary": "syntax", "suggested_fix": "fix it", "triage_source": "heuristic"}]
    assert verdict(_plan(), results, triages) == "likely red"
    text = render_report(_plan(), results, triages)
    assert "likely red" in text
    assert "CODE_BUG" in text
    assert "Not verified" in text


def test_env_mismatch_blocks_green():
    results = {"steps": [{"id": "a", "exit_code": 0, "skipped": False, "name": "unit", "log_tail": ""}]}
    plan = _plan(env_diff=[{"kind": "node_version", "expected": "20", "actual": "v18.0.0", "detail": "node major differs"}])
    assert verdict(plan, results, []) == "incomplete"
    assert "node major differs" in render_report(plan, results, [])
