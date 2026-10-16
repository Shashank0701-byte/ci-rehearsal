from triage import heuristic, redact, triage_step


def test_heuristic_classes():
    assert heuristic("SyntaxError: invalid syntax", [], None)["class"] == "CODE_BUG"
    assert heuristic("connection ECONNRESET", [], None)["class"] == "FLAKY"
    assert heuristic("boom", [{"kind": "node_version"}], None)["class"] == "ENV_MISMATCH"
    assert heuristic("boom", [], "action not executed")["class"] == "UNVERIFIABLE_LOCALLY"


def test_redacts_tokens():
    secret = "ghp_" + "a" * 36
    assert secret not in redact(f"auth {secret} failed")


def test_invalid_model_json_falls_back():
    result = triage_step("SyntaxError", [], None, complete=lambda prompt: "not-json")
    assert result["class"] == "CODE_BUG"
    assert result["triage_source"] == "heuristic"


def test_valid_model_json_is_used_and_prompt_is_redacted():
    secret = "ghp_" + "b" * 36
    seen = {}

    def complete(prompt):
        seen["prompt"] = prompt
        return '{"class":"CODE_BUG","summary":"syntax error","suggested_fix":"fix the token","confidence":0.9}'

    result = triage_step(f"token {secret}", [], None, complete=complete)
    assert result["triage_source"] == "ollama"
    assert result["summary"] == "syntax error"
    assert secret not in seen["prompt"]


def test_model_name_comes_from_env(monkeypatch):
    monkeypatch.setenv("CI_REHEARSAL_MODEL", "llama3.2:1b")
    from triage import model_name

    assert model_name() == "llama3.2:1b"
