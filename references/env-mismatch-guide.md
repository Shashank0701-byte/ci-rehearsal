# Environment mismatch guide

Use this only when the report contains an environment mismatch or the class is `ENV_MISMATCH`.

| Kind | What it means | What to do |
|---|---|---|
| `node_version` | `setup-node` major version differs from local `node -v`, or Node is missing | Install the major version the workflow pins, or change the pin |
| `python_version` | `setup-python` major.minor differs from local Python, or Python is missing | Install that Python, or change the pin |
| `os` | `runs-on` is another OS family than this machine | Treat shell-specific steps as incomplete even if they passed |
| `missing_secret` | A step or env value references `secrets.*` | CI can still fail. Do not paste a token into the repo |
| `missing_env` | A `vars.*` value is not in the local environment | Export the variable locally or accept an incomplete verdict |
| `lockfile` | `npm ci`, `poetry install`, or `uv sync` has no lockfile | Commit the lockfile the command expects |

A passing local command does not cancel these rows. The verdict stays `incomplete` until the diff is empty and every skipped check is either removed or actually run.
