# Failure patterns

Use this when classifying a step that ran and failed. The class must be one of:

- `CODE_BUG` — the log points at project code, a test assertion, a type error, a lint error, or a missing script. The local runtime matches CI.
- `ENV_MISMATCH` — versions, OS, lockfile, or required env vars differ from the workflow. Prefer this when `env_diff` is non-empty and the log is consistent with that difference.
- `UNVERIFIABLE_LOCALLY` — the failure depends on a secret, a third-party action, a service container, a matrix, or a deploy step. Do not invent a local fix that pretends the secret exists.
- `FLAKY` — the log shows a transient network or timeout failure (`ECONNRESET`, `ETIMEDOUT`, "timed out") and the same step has passed before without a code change.

Suggested fixes stay inside the class. A `CODE_BUG` fix names the file or command in the log. An `ENV_MISMATCH` fix names the version or file to align. An `UNVERIFIABLE_LOCALLY` fix tells the user what CI will still have to prove.
