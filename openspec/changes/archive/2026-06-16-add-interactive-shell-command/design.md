## Context

`microjail run` is the non-interactive workload entry point. It loads `.microjail/config.yaml`, launches the Workshop if needed, applies Lockdown, starts the workload with `MicroJail.popen(..., interactive=False)`, and supervises it through `Warden`. That path deliberately maps to `workshop exec --non-interactive`, which is correct for scripts but wrong for an interactive shell: Bash starts without a terminal prompt, line editing, or job control.

Workshop already supports interactive PTY execution through `workshop exec --interactive`, and `Workshop.popen(..., interactive=True)` already selects that flag. The new command should reuse the existing Microjail policy and supervision path while switching only the Workshop execution mode.

## Goals / Non-Goals

**Goals:**
- Add `microjail shell` as the user-facing interactive terminal entry point.
- Preserve `microjail run` behavior as non-interactive and script-safe.
- Reuse the same Lockdown application sequence as `microjail run` before starting the shell.
- Use Workshop interactive execution so the shell inherits the host terminal PTY.
- Keep Warden supervision active while the shell process runs.
- Return the shell process exit code and leave the Lockdown applied after the shell exits.

**Non-Goals:**
- Do not change `microjail run` to auto-detect TTYs or switch modes implicitly.
- Do not add automatic unlock on shell exit.
- Do not add new Capability or Gate types.
- Do not replace Workshop's shell implementation or add a custom PTY layer.
- Do not support non-interactive `microjail shell` usage as a scripting API; scripts should use `microjail run`.

## Decisions

### 1. Add a separate `shell` command instead of changing `run`

`microjail run` remains explicit non-interactive execution. `microjail shell` becomes the interactive path.

Alternative considered: make `run` infer interactive mode from stdin/stdout TTY state. Rejected because it makes the same command line behave differently under a terminal, CI, Typer tests, redirection, and agent harnesses. A separate command is stable and easier to document.

### 2. Reuse the run policy sequence

The shell command should share the same high-level sequence as `run`:

1. Resolve project and load Microjail config.
2. Launch the configured Workshop if it is not currently launched.
3. Apply Lockdown with Capabilities first and Gates second.
4. Start the shell workload.
5. Supervise through Warden.
6. Exit with the workload's exit code.

This preserves the same safety boundary: the user never reaches a shell before declared access has been provisioned and restrictions have been enforced.

Alternative considered: implement `microjail shell` as `microjail lock` followed by `workshop shell`. Rejected because it would split policy application from workload supervision and would not give Microjail direct access to the shell process handle for Warden termination behavior.

### 3. Use Workshop shell for the default path and interactive exec for overrides

When no command is provided, `microjail shell` should start Workshop's default shell directly through `workshop shell`. This matches Workshop's own default-shell selection instead of approximating it with `bash`, `$SHELL`, or another in-container resolver.

When an explicit command is provided, `microjail shell -- <command> [args...]` should use `MicroJail.popen(..., interactive=True)`, letting the Workshop adapter emit `workshop exec --interactive`.

Both paths return a `subprocess.Popen` handle, so Warden supervision and termination behavior stay centralized.

### 4. Default command and command override

`microjail shell` should default to the container's default shell, matching `workshop shell`. `microjail shell -- <command> [args...]` should allow an explicit interactive command such as `zsh` or `bash -l`.

### 5. Reject non-TTY invocation before applying policy

If stdin or stdout is not a terminal, `microjail shell` should fail with a clear error before launching the Workshop or applying Lockdown. This prevents a command named `shell` from being used accidentally in automation where no prompt can work.

Alternative considered: let Workshop decide interactive vs non-interactive behavior. Rejected because Microjail forces interactive mode for this command; failing early gives a clearer Microjail-level contract.

## Risks / Trade-offs

- **Risk:** Reusing run logic may duplicate exception handling between commands. → **Mitigation:** extract a small shared helper only if duplication becomes material; do not introduce a broad abstraction before it pays for itself.
- **Risk:** Testing real PTY behavior in unit tests is brittle. → **Mitigation:** functional tests should assert command wiring (`interactive=True`, no workload start before policy success, exit-code passthrough). Existing Workshop adapter tests cover `interactive=True` mapping to `--interactive`.
- **Risk:** Defaulting to `bash` may fail in images without Bash. → **Mitigation:** document the default and support explicit command override; the default matches the reported use case and common Workshop bases.
- **Risk:** The command name says shell but implementation uses `workshop exec --interactive`, not `workshop shell`. → **Mitigation:** the guarantee that matters is PTY-backed interactive execution under Microjail policy and Warden supervision; direct `workshop shell` would weaken implementation cohesion.
