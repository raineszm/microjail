## Context

The microjail CLI today writes plain text via `typer.echo()` across 11 command files plus `warden.py`. Rich is already declared as a dependency in `pyproject.toml` (`rich>=14.2.0`) but is never imported. The CLI surface has accumulated three prefixes — `"error: "`, `"warning: "`, `"WARN: "` — used inconsistently, and the two commands that produce structured output (`status`, `validate`) collapse their structure into indented bullet text.

The interactive session is the dominant use case: the README and demo show users running `microjail init` → `microjail shell` → `microjail exec` in a real terminal. Non-interactive use (CI, scripts, `| grep`, output capture) must continue to produce parseable plain text. The `typer.testing.CliRunner` test runner captures stdout and stderr into `StringIO` and asserts on substring matches in those captured strings.

## Goals / Non-Goals

**Goals:**
- Migrate all CLI output to a Rich-based path that auto-degrades to plain text when the stream is not a TTY.
- Collapse the three error/warning prefixes into two helpers (`error`, `warning`) with consistent styling.
- Give `status` and `validate` visually structured output (table, panel) without changing their observable behavior (substring assertions, exit codes, message wording).
- Extend `MicroJailStatus` to expose endpoint capability binding info (host endpoint, container endpoint, fatal) so the security-relevant mapping is visible at a glance.

**Non-Goals:**
- Adding a `--json` output mode. The current output is plain text by design; a JSON mode is a separate change.
- Changing exit codes, error message wording, or any other observable contract.
- Migrating the Warden loop's `print(..., file=sys.stderr)` to the new helpers. That change has additional context (Live/Status during `exec`, verbose mode) that warrants its own proposal.
- Modifying the `cap` command's success line format beyond icon prefix. The substring assertion `"endpoint capability added: inference -> localhost:8080" in result.stdout` must keep passing.
- Rendering changes for `exec` / `shell` workload I/O. That I/O is a PTY passthrough; inserting Rich styling into the workload's stream would corrupt it.
- Non-endpoint capability types. The `endpoint_capabilities` field is shaped for current types; future cap types either won't appear or will need their own field.

## Decisions

### Decision 1: Module-level Rich Console singletons in `commands/_output.py`

A single `commands/_output.py` module holds two module-level `Console` instances (default + `stderr=True`). Rich resolves `sys.stdout` and `sys.stderr` lazily, so module-level construction is safe under `typer.testing.CliRunner`, which replaces both streams before invoking commands.

**Chosen**: Two module-level `Console` instances in `commands/_output.py`. Default `Console()` writes to stdout; `Console(stderr=True)` writes to stderr.

**Considered**:
- Per-command `Console` construction. Rejected: it duplicates the configuration (`force_terminal=False`, `width=120`) and adds noise to every command.
- Injecting `Console` as a function parameter. Rejected: the `CliRunner` test pattern doesn't currently allow output injection, and we have no test for "color appears" that requires substitution.

### Decision 2: Four flat helpers — `success`, `error`, `warning`, `info`

The helper names are short because they're called from 6 command files. Each helper takes a single `message: str` and routes to the appropriate console with the appropriate style. The `error` helper prefixes with `"error: "`, `warning` with `"warning: "`, and `success` with the `✓` icon. The wording is part of the message itself (not added by the helper), so the literal substrings `"error:"` and `"warning:"` are preserved for tests.

**Chosen**: `success(msg)`, `error(msg)`, `warning(msg)`, `info(msg)`. Message text passed by the caller; helper handles styling and prefix.

**Considered**:
- Namespaced names like `console_error(msg)`. Rejected: noise without benefit; the `error` and `warning` words are unambiguous in context.
- Auto-formatting with f-string interpolation in the helper. Rejected: forces every caller to fit one signature; the explicit `error(f"cannot determine Workshop state: {exc}")` is clearer.

### Decision 3: Status and validate use Rich `Table` / `Panel`; other commands use helpers only

The visual return on Rich is concentrated in `status` and `validate` — the two commands that produce multi-section structured output. The other commands (init, lock, exec, unlock, destroy, cap) produce short success/error/warning lines, where the helper-level styling (color, icon) is the entire improvement.

**Chosen**: `status.py` and `validate.py` use `rich.table.Table` and `rich.panel.Panel`. Other commands use only the helpers.

**Considered**:
- A "single big table" wrapping the entire `status` output. Rejected: makes the cap binding table harder to nest; a top-level table with rows that include a nested table is the cleanest composition.
- A `Live` display during `validate` to show validation progress. Rejected: validate is fast; no progress UX needed.

### Decision 4: `MicroJailStatus` extended with a new field, not modified

The existing field `capabilities: tuple[str, ...]` (just names) is preserved for backward compatibility and for non-endpoint cap types. A new `endpoint_capabilities: tuple[EndpointCapabilityInfo, ...] = ()` field carries the rich view. New field at the end with a default keeps positional construction in tests working.

**Chosen**: New `EndpointCapabilityInfo` dataclass with `name`, `host_endpoint`, `container_endpoint`, `fatal`. New field on `MicroJailStatus` with default `()`.

**Considered**:
- Replacing `capabilities: tuple[str, ...]` with a richer type. Rejected: breaks the existing test fixture and the existing "name strings" view, which is useful for the test that just asserts the cap name appears.
- Making `EndpointCapabilityInfo` a `msgspec.Struct` like `ValidateError`. Rejected: it's a read-only view for status; not serialized anywhere; a `@dataclass(frozen=True)` is the right shape.

### Decision 5: Fatal marker is a red `✗` prefix on the cap name, in the same cell

A `fatal=True` capability gets a `[red]✗[/red] {name}` style on its name cell. No separate column, no new field. In non-TTY mode this renders as the literal `✗` character followed by the name, which is the assertion `"✗" in result.stdout` for the fatal case.

**Chosen**: Red `✗` prefix in the name cell, in both the data-model surface and the rendered output.

**Considered**:
- A separate `Fatal` column with `yes` / `no` text. Rejected: adds a column with the same value across many rows; takes horizontal space; "fatal" is a yes/no and visually less impactful than the marker.
- The `💀` skull marker. Rejected: out of tone for a security tool that wants to be taken seriously; `✗` matches the `error()` helper's existing icon.
- The `‼` double exclamation. Rejected: collides with the `error()` / `warning()` visual vocabulary.

### Decision 6: The Warden `print(...)` is explicitly out of scope

`warden.py:check_policies` has a `print(f"Warning: Capability policy violation: {cap.name}", file=sys.stderr)` line for non-fatal capability policy violations. Migrating it to the new `warning()` helper is a natural follow-up but is held back because:

1. The Warden loop runs once per second for the duration of a workload. Whether to show those events (and how — quiet, dim, Live display, verbose flag) is a separate UX question.
2. The test `b"warning" in result.stderr_bytes.lower()` is asserted in cap tests on a different code path. The change needs to keep that invariant or update it deliberately.

**Chosen**: Do not touch `warden.py` in this change. Document the follow-up in `proposal.md`.

**Considered**:
- Including the migration anyway with a minimal change (just `print` → `warning()`). Rejected: loses the opportunity to do the loop UX right; better as its own change.

## Risks / Trade-offs

- **Test surface depends on substring preservation.** Every existing substring assertion in `tests/functional/commands/` keeps passing only because (a) Rich strips ANSI when the output stream is not a TTY, and (b) helper messages keep the literal words (`error:`, `warning:`, `✓`, etc.) in the message text. Both behaviors are verified with a CliRunner smoke test in the design phase. A change that violates either invariant would break tests. The tasks list flags this as a regression risk to check.
- **No JSON output.** Users who want to script against `microjail status` currently grep for the section headers. A `status --json` would be a real improvement, but it expands the CLI surface and the test matrix. Out of scope for this change.
- **Visual output depends on terminal capabilities.** Rich auto-detects TTY and color depth. A terminal with no color support (rare) will still get tables and panels but no color. The table rendering is the more important visual element and works regardless of color.
- **The `✗` marker on fatal caps could be confused with the `error()` icon.** They use the same character in the same color. The visual frame (table cell vs. standalone line) and the surrounding text (`name` vs. `error: message`) disambiguate, but a user scanning output quickly could confuse them. If this becomes a real confusion in practice, follow-up work could swap the fatal marker for something distinct (a `⚠` row indicator, or the `‼`).
- **`MicroJailStatus` field ordering.** The new field is added at the end so positional construction keeps working. If a future change reorders the dataclass fields, it would break the existing test fixture. Not a problem now; just a constraint to keep in mind.
