## Context

`workshop init <name> --sdks a,b,c --base ubuntu@22.04` accepts comma-separated SDKs and an optional base image. The `workshop.init()` adapter in `src/microjail/adapters/workshop.py` already exposes a `sdks: list[str] | None` parameter (default `[]`, always appending `"direnv"`). The `microjail init` command hardcodes a call to `workshop.init(name)` without passing SDKs, base, or a project path, so users cannot request additional SDKs, a non-default base, or operate on a non-CWD project through microjail.

Additionally, Workshop has a global `--project` / `-p` flag. Microjail hardcodes `Path.cwd()` across all commands. Adding parity here makes microjail consistent with Workshop's interface model.

This change adds CLI options to forward user-requested Workshop init parameters and a global project flag to all commands.

## Goals / Non-Goals

**Goals:**
- Let users pass additional Workshop SDK names and a base image to `microjail init` for fresh initialization.
- Add a global `--project` / `-p` flag to all microjail commands, resolving to an absolute path and forwarded to Workshop subprocesses.
- Preserve the existing default SDK set (`direnv`) — user SDKs are additive.
- Forward `--project` explicitly to all `workshop` subprocess calls (including `init`, which currently does not pass it).
- Fail cleanly on invalid SDK/base names (Workshop rejects the init; microjail does not write config).

**Non-Goals:**
- SDK or base manipulation during `--adopt` (adoption attaches to an existing Workshop, does not re-init).
- Removing microjail's default SDKs.
- Validating SDK or base names (Workshop is the source of truth).

## Decisions

### `--sdks`: comma-separated string, mirrors Workshop

Use `--sdks golang,java` (singular CLI flag, comma-separated value) matching Workshop's `--sdks` shape. The adapter already accepts `list[str]`; the command layer splits the string and passes the list.

**Alternative considered:** `--sdk golang --sdk java` (repeatable singular). Rejected because microjail mirrors Workshop's CLI conventions as a thin orchestration layer.

### `--base`: optional string, omitted when unset

Use `--base ubuntu@22.04` matching Workshop's `--base` flag. When the user does not pass `--base`, microjail omits the flag from the subprocess call entirely, letting Workshop apply its own default (`ubuntu@24.04`). This avoids coupling to Workshop's default.

**Alternative considered:** Always pass `--base ubuntu@24.04` explicitly. Rejected because it hardcodes Workshop's default, which could drift stale.

### `--project` / `-p`: global Typer callback, resolved absolute

A Typer `@app.callback()` stores the resolved absolute `Path` in `ctx.obj`. Every command accepts `ctx: typer.Context` as its first parameter and uses `ctx.obj` instead of `Path.cwd()`. The callback resolves relative paths to absolute eagerly.

**Alternative considered:** `os.chdir()` in the callback, keeping `Path.cwd()` downstream. Rejected because `chdir` is process-global mutable state, fragile under concurrency, and `pathlib` caches `Path.cwd()`.

### Adapter `init()`: `project` required, `sdks`/`base` optional

```python
def init(name: str, project: Path, sdks: list[str] | None = None, base: str | None = None):
```

`project` is required — consistent with every other adapter function (`launch`, `info`, `exists`, `exec_`, etc.). The subprocess call passes `--project <project>` explicitly.

### `--adopt` behavior: `--base` warns, `--sdks` silently ignored

`--adopt` attaches microjail to an existing Workshop without re-initializing. `--base` changing the OS image is a meaningful no-op worthy of a warning. `--sdks` is less impactful and silently ignored.

### `--overwrite` forwards all flags

`overwrite_workshop()` deletes the existing Workshop YAML then calls `init(name, sdks=sdks, base=base)`, so all flags are naturally forwarded. The `init()` command function signature is extended to accept all three optional parameters.

### No init-option persistence in `.microjail/config.yaml`

SDK and base selection are Workshop creation-time concerns. Once the Workshop YAML is written, microjail has no reason to re-read or re-apply them. The Lockdown configuration remains init-option-agnostic. The `--project` flag is a runtime concern, not persisted.

### Commands wired explicitly (not via `app.command()` decorator)

Each command function gains `ctx: typer.Context` as its first parameter. The Typer wiring stays explicit (`app.command("init")(init)`) in `cli.py`. The callback sets `ctx.obj = resolved_project_path`.

## Risks / Trade-offs

- **Global `--project` inflates every command signature** → Every command gains a `ctx` parameter. Acceptable because the change is mechanical and improves testability (commands no longer depend on process-global `cwd`).
- **Silent ignore of `--sdks` during `--adopt`** → Users who expect `--sdks` to add SDKs to an existing Workshop will be surprised. Mitigation: documented behavior. `--base` warns, which covers the higher-impact case.
- **No SDK/base validation** → Invalid names surface as Workshop init failures (non-zero exit, error message). microjail does not write `.microjail/config.yaml` on failure. Acceptable because Workshop is authoritative.
- **All adapter functions must pass `--project`** → `init()` is the only adapter function that currently omits `--project`. All others (`launch`, `info`, `exec_`, etc.) already pass it. This change fixes the inconsistency.

## Open Questions

None.
