from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _frontmatter():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    block = text[4:end]
    data = {}
    for line in block.splitlines():
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    body = text[end + 5 :]
    return data, body


def test_skill_frontmatter_matches_agentskills_rules():
    data, body = _frontmatter()
    assert data["name"] == "ci-rehearsal"
    assert data["name"] == ROOT.name
    description = data["description"]
    assert "GitHub Actions" in description
    assert "when" in description.lower() or "Use when" in description
    assert len(description) <= 1024
    assert data["license"] == "MIT"
    assert "Python 3.10+" in data["compatibility"]
    assert "Ollama" in data["compatibility"]
    assert len(body.splitlines()) < 500
