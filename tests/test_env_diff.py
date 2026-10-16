from pathlib import Path

from parse_workflows import parse_workflows

WORKFLOW = """\
name: ci
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      PUBLIC: literal
      MISSING: ${{ vars.MISSING }}
      NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
    steps:
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: npm ci
"""


def test_env_diff_flags_version_os_secret_var_and_lockfile(tmp_path: Path):
    directory = tmp_path / ".github" / "workflows"
    directory.mkdir(parents=True)
    (directory / "ci.yml").write_text(WORKFLOW, encoding="utf-8")
    probe = {
        "node": "v18.20.0",
        "python": "3.13.5",
        "system": "Windows",
        "env": {"PUBLIC": "literal"},
    }
    plan = parse_workflows(tmp_path, probe=probe)
    kinds = {item["kind"] for item in plan["env_diff"]}
    assert {"node_version", "python_version", "os", "missing_secret", "missing_env", "lockfile"} <= kinds


def test_matching_environment_has_no_diff(tmp_path: Path):
    workflow = """\
name: ci
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm test
"""
    directory = tmp_path / ".github" / "workflows"
    directory.mkdir(parents=True)
    (directory / "ci.yml").write_text(workflow, encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    probe = {"node": "v20.11.1", "python": "3.11.0", "system": "Linux", "env": {}}
    plan = parse_workflows(tmp_path, probe=probe)
    assert plan["env_diff"] == []
