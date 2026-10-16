from pathlib import Path

import pytest

from parse_workflows import parse_workflows


def write_workflow(root: Path, name: str, text: str) -> None:
    directory = root / ".github" / "workflows"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


NODE_CI = """\
name: node
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: unit
        run: npm test
"""

PYTHON_CI = """\
name: python
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: unit
        run: pytest
"""

PATHS_CI = """\
name: paths
on:
  push:
    paths:
      - "src/**"
    paths-ignore:
      - "docs/**"
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
    steps:
      - run: npm test
"""

PUBLISH_CI = """\
name: publish
on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Publish package
        run: npm publish
      - name: unit
        run: npm test
"""

MATRIX_CI = """\
name: matrix
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node: ["18", "20"]
    steps:
      - run: npm test
"""

REUSABLE_CI = """\
name: reusable
on: push
jobs:
  call:
    uses: org/repo/.github/workflows/ci.yml@main
"""


def test_parses_node_and_python_jobs(tmp_path):
    write_workflow(tmp_path, "node.yml", NODE_CI)
    write_workflow(tmp_path, "python.yml", PYTHON_CI)
    plan = parse_workflows(tmp_path, probe=None)

    jobs = {job["name"]: job for job in plan["jobs"]}
    assert jobs["test"]["runs_on"] in ("ubuntu-latest", "ubuntu-latest")
    node_jobs = [job for job in plan["jobs"] if job["runtime"]["node"] == "20"]
    python_jobs = [job for job in plan["jobs"] if job["runtime"]["python"] == "3.11"]
    assert len(node_jobs) == 1
    assert len(python_jobs) == 1

    run_steps = [step for step in plan["steps"] if step["kind"] == "run" and step["verifiable"]]
    assert {step["script"] for step in run_steps} >= {"npm test", "pytest"}
    uses = [item for item in plan["unverifiable"] if "checkout" in item["item"] or "setup-node" in item["item"]]
    assert uses


def test_extracts_paths_and_secrets(tmp_path):
    write_workflow(tmp_path, "paths.yml", PATHS_CI)
    plan = parse_workflows(tmp_path, probe=None)
    job = plan["jobs"][0]
    assert job["paths"] == ["src/**"]
    assert job["paths_ignore"] == ["docs/**"]
    assert "NPM_TOKEN" in job["secrets"]
    assert any(item["item"] == "NPM_TOKEN" for item in plan["unverifiable"])


def test_skips_publish_and_keeps_unit_test(tmp_path):
    write_workflow(tmp_path, "publish.yml", PUBLISH_CI)
    plan = parse_workflows(tmp_path, probe=None)
    by_script = {step["script"]: step for step in plan["steps"]}
    assert by_script["npm publish"]["verifiable"] is False
    assert "publish" in by_script["npm publish"]["skip_reason"]
    assert by_script["npm test"]["verifiable"] is True


def test_matrix_and_reusable_workflows_are_unverifiable(tmp_path):
    write_workflow(tmp_path, "matrix.yml", MATRIX_CI)
    write_workflow(tmp_path, "reusable.yml", REUSABLE_CI)
    plan = parse_workflows(tmp_path, probe=None)
    reasons = " ".join(item["reason"] for item in plan["unverifiable"])
    assert "matrix" in reasons
    assert "reusable" in reasons
    assert all(step["verifiable"] is False for step in plan["steps"])


def test_invalid_yaml_does_not_drop_other_files(tmp_path):
    write_workflow(tmp_path, "good.yml", NODE_CI)
    write_workflow(tmp_path, "bad.yml", "jobs: [\n")
    plan = parse_workflows(tmp_path, probe=None)
    assert any(step["script"] == "npm test" for step in plan["steps"])
    assert any("bad.yml" in item["item"] for item in plan["unverifiable"])


def test_yaml_on_key_is_not_dropped(tmp_path):
    write_workflow(tmp_path, "node.yml", NODE_CI)
    plan = parse_workflows(tmp_path, probe=None)
    assert plan["jobs"][0]["triggers"] == ["push"]


def test_missing_workflows_are_reported(tmp_path):
    plan = parse_workflows(tmp_path, probe=None)
    assert plan["jobs"] == []
    assert plan["unverifiable"]
