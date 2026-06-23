## Purpose

Provide shared CLI output infrastructure: module-level Rich Console singletons for stdout/stderr and four message helpers (success, error, warning, info) used by every CLI command.

---

## Requirements

### Requirement: CLI output uses two module-level Rich Console singletons

The system SHALL provide two module-level `rich.console.Console` instances in `src/microjail/commands/_output.py`: one writing to `sys.stdout` (for success and informational output) and one writing to `sys.stderr` (for errors and warnings). Both instances SHALL resolve `sys.stdout` / `sys.stderr` lazily so the streams picked up are the streams active at print time, not at module-import time. Both instances SHALL emit ANSI escape sequences only when the destination stream is a TTY; when piped to a non-TTY file, output SHALL be plain text with no escape codes.

#### Scenario: Module-level Console instances are constructed at import time
- **WHEN** `microjail.commands._output` is imported
- **THEN** two `rich.console.Console` instances are created
- **AND** both instances are module-level attributes (importable as `_output.stdout_console` and `_output.stderr_console`)

#### Scenario: Non-TTY output contains no ANSI escape sequences
- **GIVEN** the `Console` instances are writing to a `StringIO` buffer (e.g. under `typer.testing.CliRunner`)
- **WHEN** a styled `console.print(...)` call is made
- **THEN** the captured buffer contains no `\x1b[` escape sequences
- **AND** the captured buffer contains the visible message text verbatim

---

### Requirement: CLI output exposes four message helpers

The system SHALL provide four helper functions in `src/microjail/commands/_output.py`: `success`, `error`, `warning`, and `info`. Each helper takes a single `message: str` argument and prints it to the appropriate Console with a consistent visual prefix.

#### Scenario: success helper writes to stdout with a checkmark prefix
- **WHEN** `success("endpoint capability added: inference")` is called
- **THEN** the message is written to the stdout Console
- **AND** the rendered output contains the `✓` character immediately before the message text
- **AND** no other helper is called

#### Scenario: error helper writes to stderr with a red cross prefix
- **WHEN** `error("cannot determine Workshop state")` is called
- **THEN** the message is written to the stderr Console
- **AND** the rendered output contains the literal text `error:` followed by the message
- **AND** the cross icon is rendered in red

#### Scenario: warning helper writes to stderr with a yellow triangle prefix
- **WHEN** `warning("live Workshop state not changed")` is called
- **THEN** the message is written to the stderr Console
- **AND** the rendered output contains the literal text `warning:` followed by the message
- **AND** the triangle icon is rendered in yellow

#### Scenario: info helper writes to stdout with no prefix
- **WHEN** `info("Not initialized. Run 'microjail init' first.")` is called
- **THEN** the message is written to the stdout Console
- **AND** the rendered output contains the message text with no leading icon or prefix

---

### Requirement: Helpers preserve the literal substrings that existing tests assert on

The system SHALL arrange the helper output so that the substrings asserted on by existing functional tests remain present in the captured output. In particular, `error("...")` output SHALL contain the literal `error:` prefix and the literal `warning:` text, and `warning("...")` output SHALL contain the literal `warning:` text.

#### Scenario: error output contains "error:" substring
- **WHEN** `error("cannot determine Workshop state: connection refused")` is called
- **THEN** the captured stderr contains the substring `error: cannot determine Workshop state`
- **AND** the captured stderr contains the substring `connection refused`

#### Scenario: warning output contains "warning:" substring (case-insensitive)
- **WHEN** `warning("live Workshop state was not changed")` is called
- **THEN** the captured stderr (lower-cased) contains the substring `warning:`

#### Scenario: success output contains the message substring verbatim
- **WHEN** `success("endpoint capability added: inference -> localhost:8080")` is called
- **THEN** the captured stdout contains the substring `endpoint capability added: inference -> localhost:8080`
