## Why

The `Warden` (in `src/microjail/warden.py`) currently monitors policy invariants by polling each gate and capability on a fixed interval. Polling is wasteful for changes that the LXD daemon already broadcasts in real time (lifecycle events, device changes, state transitions), and a polling-based Warden cannot notice a violation between polls — a workload could detach a network device and re-attach it in the gap without the Warden ever seeing the violation. The `refactor/event-warden-retry` branch exists to replace polling with an event-driven Warden, but that work is blocked on a missing primitive: a reliable, testable library for streaming LXD events for a single container. This change introduces that primitive. Wiring it into the Warden is a separate, follow-up change — this one stops at the library boundary.

## What Changes

- Add a new adapter module `src/microjail/adapters/lxd_monitor.py` that owns a long-lived `lxc monitor` subprocess and exposes a Pythonic, thread-safe interface to its events.
- The adapter spawns `lxc monitor --project=<project> --type=lifecycle --format=json` (or the closest equivalent supported by the installed `lxc` client), reads its stdout line-by-line on a background thread, parses each line as JSON, and pushes matching events onto an internal queue.
- The adapter scopes itself to a single `(container_name, lxd_project)` pair. Events for any other container, or for a different LXD project, are dropped on the producer side before reaching the queue.
- The adapter provides lifecycle methods: `start()` to spawn the subprocess, `stop(timeout)` to terminate it, and `events(timeout)` to retrieve the next matching event (blocking up to `timeout` seconds, or returning `None` on timeout).
- If the subprocess exits unexpectedly, the adapter exposes a `last_exception` attribute carrying the underlying error; callers (the future Warden) decide what to do with that signal. Reconnection / retry is **out of scope** for this change.
- The adapter is unit-testable without a real LXD daemon: the subprocess launcher is injected (matching the `CommandExecutor` pattern already in `src/microjail/adapters/workshop.py`), and the parser is pure-Python and exercised directly.
- No changes to `Warden`, `MicroJail`, the gate/capability protocols, the CLI, or any other adapter. The existing `warden-monitoring` spec is unchanged.

## Capabilities

### New Capabilities
- `lxd-event-monitor`: A `LxdMonitor` class that subscribes to LXD lifecycle events for a single container via an `lxc monitor` subprocess, filters them to that container and project, and exposes a thread-safe queue of matching events along with a `last_exception` for unrecoverable subscription loss.

### Modified Capabilities
- None. The `warden-monitoring` polling spec and the `gate-and-capability-protocols-split-check-and-verify` ADR both stay as they are. This change adds a building block; integrating it into the Warden is a separate, later change.

## Impact

- **New file**: `src/microjail/adapters/lxd_monitor.py` (~150 LOC). Defines `LxdMonitor`, a `LxdMonitorError` exception class, and a `MonitorLauncher` protocol for test injection.
- **New tests**: `tests/unit/adapters/test_lxd_monitor.py`. Covers the constructor defaults, event filtering (container + project match), JSON parse failures being dropped, queue behavior under timeout, subprocess-failure path populating `last_exception`, and `stop()` tearing the thread down cleanly. No `lxc` binary on `$PATH` required; tests use a fake `MonitorLauncher` that yields preset lines.
- **No production callers in this change.** The library is shipped unused; the next change on `refactor/event-warden-retry` (or equivalent) will wire `LxdMonitor` into `Warden`.
- **No new runtime dependencies.** Uses only `subprocess`, `queue`, `threading`, `json`, and `contextlib` from the stdlib, plus `microjail.exceptions.MicrojailError` for the exception base.
- **No public API breakage.** The new module is additive; nothing existing is renamed, moved, or has its signature changed.
- **No CLI surface changes.** `lxc monitor` runs as a child process; its lifecycle is invisible to the user.
