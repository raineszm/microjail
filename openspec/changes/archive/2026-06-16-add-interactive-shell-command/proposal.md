## Why

`microjail run -- bash` currently executes through Workshop non-interactive mode, so interactive shells do not receive a PTY and users see no usable prompt. Operators need a first-class interactive shell entry point that preserves Microjail's Lockdown application and Warden supervision guarantees instead of bypassing policy with `workshop shell`.

## What Changes

- Add a `microjail shell` CLI command for interactive terminal sessions inside the configured Workshop environment.
- Apply the same pre-workload guarantees as `microjail run`: launch Workshop if needed, provide declared Capabilities, enforce Gates, and only then start the shell.
- Run the shell through Workshop interactive execution so the workload inherits the host terminal PTY.
- Supervise the interactive shell with the Warden while it runs, preserving runtime Gate and fatal Capability policy handling.
- Preserve the shell process exit code and leave policy applied after the shell exits; no automatic unlock.
- Keep `microjail run` non-interactive so script and CI behavior remain deterministic.

## Capabilities

### New Capabilities
- `interactive-shell-command`: User-facing interactive shell command semantics and safety guarantees.

### Modified Capabilities
- *(none — `microjail shell` consumes existing Workshop interactive execution without changing the Workshop popen contract.)*

## Impact

- Affected CLI surface: new `microjail shell` command.
- Affected code: `src/microjail/cli.py`, new or reused command implementation under `src/microjail/commands/`, and tests under `tests/functional/commands/` plus any focused adapter/CLI coverage needed.
- Affected docs: README usage section for interactive shells.
- No new runtime dependencies.
- No breaking changes to `microjail run`.
