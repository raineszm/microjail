# Implementation Tasks

## Slice 1: Tracer Bullet - cli-output-foundation (helpers + first call-site swap)

The minimum end-to-end path: `_output.py` module with both Consoles and all four helpers, plus a small call-site swap in `init.py` that proves (a) lazy stream resolution works under `CliRunner`, (b) the helpers preserve the substrings tests assert on, and (c) ANSI does not leak to non-TTY streams.

- **Test**: `test_init_delegates_to_workshop_and_writes_config` in `tests/functional/commands/test_init.py` (proves `success()` writes to stdout and preserves `"Adopted"` substring)
- **Test**: `test_init_workshop_failure_exits_nonzero_without_config` in `tests/functional/commands/test_init.py` (proves `error()` writes to stderr and preserves `"Failed to initialize Workshop"` substring)
- **Test**: `test_init_overwrite_warns_if_doesnt_exist` in `tests/functional/commands/test_init.py` (proves `warning()` writes to stderr and preserves `"WARN:"` substring)
- **Arrange**:
  - Create `src/microjail/commands/_output.py` exposing `stdout_console`, `stderr_console`, and the four helpers (`success`, `error`, `warning`, `info`).
  - `stdout_console = Console(width=200)` and `stderr_console = Console(stderr=True, width=200)`, both module-level.
  - The `error` helper prints `f"[red]✗[/red] error: {message}"` to `stderr_console`.
  - The `warning` helper prints `f"[yellow]⚠[/yellow] warning: {message}"` to `stderr_console`.
  - The `success` helper prints `f"[green]✓[/green] {message}"` to `stdout_console`.
  - The `info` helper prints `message` to `stdout_console` with no prefix.
  - In `src/microjail/commands/init.py`, swap three call sites:
    - `typer.echo(f"Adopted workshop {name}")` → `success(f"Adopted workshop {name}")`
    - `typer.echo(f"WARN: --base is ignored during adopt", err=True)` → `warning("--base is ignored during adopt")`
    - `typer.echo(f"Failed to initialize Workshop '{name}': {exc}", err=True)` → `error(f"Failed to initialize Workshop '{name}': {exc}")`
- **Act**: Run `uv run pytest tests/functional/commands/test_init.py -k "delegates or failure or overwrite" -v`
- **Assert**:
  - All three tests pass with no test-file changes
  - Captured `result.stdout` for the adopt case contains the substring `Adopted` and the `✓` character
  - Captured `result.stderr` for the failure case contains the substring `Failed to initialize Workshop` and no `\x1b[` escape sequences
  - Captured `result.stderr` for the overwrite case contains the substring `WARN:` and no `\x1b[` escape sequences

- [x] 1.1 RED: Add a unit test `test_helpers_emit_plain_text_under_non_tty` in `tests/unit/test_output.py` (new file) that captures stdout and stderr via pytest's `capsys` fixture, calls each of the four helpers, and asserts no `\x1b[` escape sequences appear and the message substrings (`"error:"`, `"warning:"`, `"✓"`) are present.
- [x] 1.2 GREEN: Create `src/microjail/commands/_output.py` with the two Consoles (width=200 to prevent Rich word-wrap in non-TTY mode under CliRunner) and the four helpers. Swap the three `init.py` call sites listed above. Confirm all three functional tests pass and the unit test passes.
- [x] 1.3 REFACTOR: Imports alphabetical, ruff clean, no message-wording drift. Confirmed only the three call-site swaps changed in `init.py`.

## Slice 2: Migrate remaining call sites in init/lock/unlock/destroy/cap

Replace every `typer.echo("error: ...", err=True)` with `error(...)`, every `typer.echo("warning: ...", err=True)` and `typer.echo("WARN: ...", err=True)` with `warning(...)`, and every success line with `success(...)` across `init.py`, `lock.py`, `unlock.py`, `destroy.py`, `cap.py`, `exec.py`, `shell.py`, `supervision.py`, `status.py`, and `validate.py`. Verify with the full functional test suite.

- [x] 2.1 RED: existing test assertions on output substrings serve as the regression net.
- [x] 2.2 GREEN: Mechanical swap in all 10 command files. Cap `preflight_workshop_state` signature changed to keyword-only args; one rewording (stopped/off warning) preserved verbatim.
- [x] 2.3 REFACTOR: ruff check clean. All 210 unit/functional tests pass.

## Slice 3: MicroJailStatus extension (EndpointCapabilityInfo + endpoint_capabilities)

Add `EndpointCapabilityInfo` dataclass with `name`, `host_endpoint`, `container_endpoint`, `fatal` fields. Add `endpoint_capabilities: tuple[EndpointCapabilityInfo, ...] = ()` field at the end of `MicroJailStatus`. Update `MicroJail.status()` to populate the new field by iterating `self.lockdown.caps` and projecting `WorkshopEndpointCapability` instances (using `cap.resolved_endpoint` for the container-side value).

- [x] 3.1 RED: Add two unit tests in `tests/unit/test_microjail.py` (one for the new field, one for the dataclass defaults).
- [x] 3.2 GREEN: Add `EndpointCapabilityInfo` dataclass and `endpoint_capabilities` field on `MicroJailStatus` (default `()`). Update `MicroJail.status()` to populate from `WorkshopEndpointCapability` instances using `cap.resolved_endpoint`.
- [x] 3.3 REFACTOR: ruff clean, 212 tests pass.

## Slice 4: status.py rewrite with Rich Table and nested cap table

Render `microjail status` output as a `rich.table.Table` with sections for workshop, capabilities (as a nested table showing name, host endpoint, container endpoint, with red `✗` prefix on fatal cap names), gates, and connections. Preserve all existing substring assertions on `result.stdout` (`"test-jail"`, `"ready"`, `"inference"`, `"network-egress"`, `"Not initialized"`).

- [x] 4.1 RED: existing substring assertions in `tests/functional/commands/test_status.py` (and Slice 3's new unit tests) serve as the regression net.
- [x] 4.2 GREEN: Rewrite `status.py` with a Rich `Table` showing workshop, capabilities (as a nested table with name, host endpoint, container endpoint; red `✗` on fatal), gates, and connections. In non-TTY mode the table renders as plain text and the substrings stay intact.
- [x] 4.3 REFACTOR: 212 tests pass, ruff clean.

## Slice 5: validate.py rewrite with Rich Panel per error

Render each `ValidateError` as a `rich.panel.Panel` with `kind` as the title and the message body containing the hint as a dim inline line. Preserve all existing substring assertions on `result.stderr` (`"duplicate"`, `"Not initialized"`, `"valid"` in stdout for the success case).

- [x] 5.1 RED: existing substring assertions in `tests/functional/commands/test_validate.py` (including `assert "duplicate" in result.stderr.lower()` and `assert "valid" in result.stdout.lower()`) serve as the regression net.
- [x] 5.2 GREEN: Rewrite `validate.py` to render each `ValidateError` as a Rich `Panel` with `kind` as the title and the hint as a dim inline line under the message body.
- [x] 5.3 REFACTOR: 212 tests pass, ruff clean.

## Slice 6: test_status.py fixture update for endpoint_capabilities

Update the existing `test_status_displays_workshop_state` test fixture to populate the new `endpoint_capabilities` field with both a non-fatal and a fatal cap. Add assertions for the host/container endpoint substrings and the `✗` fatal marker character.

- [x] 6.1 RED: Existing test asserts on substrings. New assertions added: `127.0.0.1:8080`, `10.0.0.1:443`, `api:443`, `✗`.
- [x] 6.2 GREEN: Updated `test_status_displays_workshop_state` to populate `endpoint_capabilities` with two entries (one fatal, one not) and added assertions for the host/container endpoint substrings and the `✗` fatal marker.
- [x] 6.3 REFACTOR: 212 tests pass, ruff clean.
