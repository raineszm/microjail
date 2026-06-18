## Why

`microjail` ships a CLI that today writes plain text via `typer.echo`. Every status line, error, and warning is unstructured. Rich is already declared in `pyproject.toml` but never imported — the intent to use it is in place, the migration isn't. The result is a CLI that shows the same information it would with Rich, but harder to scan, harder to debug, and visually indistinguishable between routine success and important failure. Two commands in particular — `status` and `validate` — produce multi-section structured output that loses most of its structure on the terminal.

## What Changes

- Add `src/microjail/commands/_output.py` with module-level Rich `Console` singletons and four helpers (`success`, `error`, `warning`, `info`). The helpers replace ad-hoc `"error: "`, `"warning: "`, and `"WARN: "` prefixes across the CLI. Output is auto-styled when stdout/stderr is a TTY and degrades to plain text otherwise, so substring assertions in existing tests keep passing unchanged.
- Add `EndpointCapabilityInfo` dataclass and a new `endpoint_capabilities` field on `MicroJailStatus`. `MicroJail.status()` populates the new field from the loaded `WorkshopEndpointCapability` objects (using the existing `resolved_endpoint` property to handle the `container_endpoint or host_endpoint` case). The new field has a default of `()`, so existing positional construction in tests keeps working.
- Rewrite `status.py` to render a Rich `Table` with a nested cap table that shows each endpoint capability's name, host endpoint, and container endpoint. Capabilities with `fatal=True` get a red `✗` prefix on the cap name.
- Rewrite `validate.py` to render each error as a Rich `Panel` with `kind` as the title and the hint inline (dim "Hint:" line under the message body).
- Replace every `typer.echo("error: ...", err=True)` / `typer.echo("warning: ...", err=True)` / `typer.echo("WARN: ...", err=True)` / `typer.echo("lock applied: ...")` / etc. in `init.py`, `lock.py`, `unlock.py`, `destroy.py`, and `cap.py` with calls to the new helpers. The visible message text is preserved (the words `error:`, `warning:`, etc. remain in the message itself), so test substring assertions survive.
- Update `tests/functional/commands/test_status.py` to populate the new `endpoint_capabilities` field on the test fixture and add assertions for host/container endpoint rendering and the fatal marker.

### Follow-up (out of scope for this change)

- `warden.py:check_policies` currently uses a bare `print(f"Warning: ...", file=sys.stderr)` for non-fatal capability policy violations. Migrating that line to the new `warning()` helper is a natural follow-up. It is not included here because the Warden loop also has separate open questions (Live/Status context, verbose mode) that warrant their own change. The substring assertion `b"warning" in result.stderr_bytes.lower()` in cap tests would need to be preserved or updated as part of that follow-up.

## Capabilities

### New Capabilities

- `cli-output-foundation`: Module-level Rich Console singletons and message helpers (`success`, `error`, `warning`, `info`) used across CLI commands. The Console pair resolves `sys.stdout` / `sys.stderr` lazily and auto-strips ANSI when the stream is not a TTY, so piped output and CliRunner-captured output render as plain text.

### Modified Capabilities

- `status-command`: Extend the `MicroJailStatus` data model with `endpoint_capabilities: tuple[EndpointCapabilityInfo, ...] = ()` and the rendering requirements that show host endpoint → container endpoint binding and mark fatal capabilities. The existing "not initialized", "workshop info", "gates", and "live tunnel connections" requirements are unchanged.
- `validate-command`: No spec-level requirement changes. The panel-rendering change is a rendering choice, not a behavior change — the existing requirements for schema conformance, duplicate names, endpoint syntax/name format, valid summary, and read-only execution are all preserved. No delta spec needed; this is listed for traceability of the implementation change.

## Impact

- **src/microjail/commands/_output.py**: New module, ~30 LOC. Two `Console` instances and four helpers.
- **src/microjail/commands/status.py**: Rewrite of the rendering block. Behavior (what data is shown) is unchanged; the rendering model is upgraded from `echo` of bullet text to Rich `Table` with a nested cap table.
- **src/microjail/commands/validate.py**: Rewrite of the rendering block. Errors now render as a `Panel` per error. Message text and exit codes unchanged.
- **src/microjail/commands/init.py**, **lock.py**, **unlock.py**, **destroy.py**, **cap.py**: Mechanical swap of `typer.echo("error: ...", err=True)` → `error(...)`, `typer.echo("warning: ...", err=True)` → `warning(...)`, `typer.echo("WARN: ...", err=True)` → `warning(...)`, success lines → `success(...)`. No message wording changes.
- **src/microjail/microjail.py**: New `EndpointCapabilityInfo` dataclass. `MicroJailStatus` gains one field with a default. `MicroJail.status()` populates the new field by iterating `self.lockdown.caps` and projecting `WorkshopEndpointCapability` instances.
- **tests/functional/commands/test_status.py**: Test fixture updated to populate `endpoint_capabilities` with both a non-fatal and a fatal cap. New assertions for host/container endpoint substrings and the fatal marker character.
- **No new dependencies.** Rich is already declared in `pyproject.toml`.
- **No public API breakage.** The new dataclass field has a default. All other changes are internal rendering.
