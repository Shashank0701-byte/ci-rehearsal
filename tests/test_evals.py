import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

from run_evals import build_rows, load_cases, render_results, score


def test_skill_context_beats_log_only():
    cases = load_cases()
    bare = score(cases, lambda case: __import__("run_evals").predict_bare(case))
    skill = score(cases, lambda case: __import__("run_evals").predict_with_context(case))
    assert bare["total"] == 16
    assert skill["correct"] > bare["correct"]
    assert skill["correct"] == skill["total"]


def test_results_table_mentions_both_conditions(tmp_path):
    rows = build_rows(load_cases(), probe_model=False)
    text = render_results(rows)
    assert "bare heuristic" in text
    assert "skill heuristic" in text
    assert "Hallucinated-fix rate" in text
    assert "Ollama not reachable" in text
