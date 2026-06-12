## Context

Currently, running `microjail run` in a newly initialized project requires the user to manually run `workshop launch` first. If they do not, the command fails with a `WorkshopNotLaunchedError` because the underlying Workshop LXD container does not exist.

## Goals / Non-Goals

**Goals:**
- Automatically detect if the Workshop has not been launched when invoking `microjail run`.
- Launch the Workshop container dynamically if it is not currently launched.
- Print a friendly status message indicating that the workshop is launching.

**Non-Goals:**
- Auto-launching workshops on commands other than `microjail run` (such as `microjail lock` or `microjail unlock`).
- Changing the error behavior when the workshop exists but is in a non-ready/unusable state (which raises `WorkshopNotReadyError`).

## Decisions

### Decision 1: Perform check and launch in `microjail run` CLI command handler
- **Rationale**: The CLI command handler is the entrypoint for user interaction. Putting the check there ensures that low-level APIs like `MicroJail.ensure()` or `MicroJail.popen()` still enforce the correct constraints and raise expected exceptions (which unit tests rely on), while the CLI wrapper handles the user journey.
- **Alternatives Considered**:
  - *Automate inside `MicroJail.ensure()`*: This would change the behavior of lower-level APIs and break existing unit tests (e.g. `test_lockdown_application.py` expects `ensure` to raise `WorkshopNotLaunchedError`).

### Decision 2: Use `microjail.workshop_info()` to determine launch status
- **Rationale**: `microjail.workshop_info()` queries the adapter to return `WorkshopInfo` (if launched) or `None` (if not launched). This is a clean, non-raising check that can determine if `workshop.launch()` needs to be executed.

## Risks / Trade-offs

- **[Risk]**: Auto-launching might take a few seconds and block the initial run.
  - *Mitigation*: Output `Launching workshop <name>...` to inform the user why there is a delay.
- **[Risk]**: Launch failure might leave the project in a half-configured state.
  - *Mitigation*: Standard subprocess error handling will bubble up the `CalledProcessError` from the launcher, exiting the CLI with a non-zero code.
