## Why

Running `microjail run` on a fresh microjail project fails with an error if the workshop has not been launched yet. Automatically launching the workshop if needed simplifies the user workflow and provides a smoother user experience.

## What Changes

- Modify the `microjail run` CLI command to check if the target workshop is launched.
- If the workshop is not launched, automatically run the workshop launch command before applying lockdown and running the workload.
- Print a user-friendly message when auto-launching (e.g. `Launching workshop <name>...`).

## Capabilities

### New Capabilities

### Modified Capabilities
- `user-facing-test-coverage`: Add requirement that `microjail run` automatically launches the workshop if it is not currently launched.

## Impact

- `src/microjail/commands/run.py`: `run` command will check workshop status and trigger launch if missing.
- `tests/e2e/test_run_e2e.py` or new tests: Add test coverage for run command auto-launch behavior.
