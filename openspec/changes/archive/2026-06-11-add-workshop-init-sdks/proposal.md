## Why

`microjail init` always creates a Workshop with only microjail's default SDK set, so users must manually edit Workshop configuration when their project needs additional SDKs or a non-default base image at environment creation time. Init-time Workshop option parity keeps the Workshop definition reproducible through the microjail CLI instead of requiring post-init hand edits.

## What Changes

- Add `microjail init` options for specifying additional Workshop SDKs (`--sdks`) and base image (`--base`) during fresh initialization. Both mirror Workshop's own flag names and shapes.
- Add a global `--project` / `-p` flag to all microjail commands, resolving to an absolute path and forwarded to Workshop subprocesses. This decouples microjail from `$CWD` and matches Workshop's top-level `--project` flag.
- Forward the requested options to Workshop initialization while preserving microjail's existing default SDK behavior (`direnv` always included).
- Keep adoption behavior: `--adopt` attaches microjail to an existing Workshop and warns when `--base` is passed (it has no effect). `--sdks` is silently ignored during adopt.
- Report Workshop initialization failures without writing `.microjail/config.yaml`, including failures caused by invalid or unavailable SDK names or base images.
- Forward `--sdks` and `--base` through `--overwrite`, which re-initializes the Workshop.

## Capabilities

### New Capabilities
- `workshop-init-options`: Covers user-facing selection of additional Workshop SDKs (`--sdks`) and base image (`--base`) during `microjail init`, and the contract for forwarding those options to Workshop.
- `workshop-project-flag`: Covers the global `--project` / `-p` flag on all microjail commands, resolution to an absolute path, and forwarding to Workshop subprocess calls.

### Modified Capabilities
- `user-facing-test-coverage`: Initialization command coverage must include init-option forwarding and `--project` resolution so the user-facing contract is tested without requiring real Workshop execution.

## Impact

- CLI/API: `microjail init` gains `--sdks` (comma-separated string) and `--base` (optional string). All commands gain global `--project` / `-p` (resolved to absolute `Path`).
- Code: affects `src/microjail/commands/init.py`, `src/microjail/commands/lock.py`, `src/microjail/commands/run.py`, `src/microjail/commands/unlock.py`, `src/microjail/adapters/workshop.py`, and Typer command wiring through `src/microjail/cli.py`.
- Tests: functional command tests should assert option forwarding, default behavior preservation, `--project` resolution, adopt-warn behavior, and failure behavior.
- Docs: README init usage should mention `--sdks`, `--base`, and the global `--project` flag.
