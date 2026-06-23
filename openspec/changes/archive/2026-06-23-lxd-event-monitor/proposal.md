## Why

The `Warden` in `src/microjail/warden.py` currently monitors policy invariants by polling each gate and capability on a fixed interval. Polling is wasteful for changes that the LXD daemon already broadcasts in real time (lifecycle events, device changes, state transitions), and a polling-based Warden cannot notice a violation between polls — a workload could detach a network device and re-attach it in the gap without the Warden ever seeing the violation. The `refactor/event-warden-retry` branch exists to replace polling with an event-driven Warden, but that work is blocked on a missing primitive: a small, testable library for streaming LXD events for a single container. This change introduces that primitive. Wiring it into the Warden is a separate, follow-up change.

## What Changes

- Add a new adapter module `src/microjail/adapters/lxd_monitor.py` that owns a long-lived `lxc monitor` subprocess and exposes the events as a blocking Python iterator.
- The adapter spawns `lxc monitor --project=<project> --type=lifecycle --format=json`, reads its stdout line-by-line in the caller's thread, parses each line as JSON, and yields matching events one at a time.
- The adapter scopes itself to a single `(container_name, lxd_project)` pair. Events for any other container, or for a different LXD project, are filtered out inside `__next__` before the iterator yields.
- The adapter is a context manager: `__enter__` returns `self`, `__exit__` calls `close()`. `close()` terminates the subprocess and is idempotent. EOF (subprocess exit, crash, or termination) raises `StopIteration` so the surrounding `for` loop exits cleanly.
- The adapter is unit-testable without a real LXD daemon: the subprocess launcher is injected via the `CommandExecutor` protocol (already used by `workshop.py`), and the parser is pure-Python and exercised directly.
- No changes to `Warden`, `MicroJail`, the gate/capability protocols, the CLI, or any other adapter. The existing `warden-monitoring` spec is unchanged.
- Threading and queueing are deliberately out of scope. A future caller that wants parallel consumption can wrap the iterator in a thread + queue; the library does not anticipate that need.

## Capabilities

### New Capabilities
- `lxd-event-monitor`: A `LxdMonitor` class that subscribes to LXD lifecycle events for a single container via an `lxc monitor` subprocess, filters them to that container and project, and exposes the matching events as a blocking iterator.

### Modified Capabilities
- None. The `warden-monitoring` polling spec and the `gate-and-capability-protocols-split-check-and-verify` ADR both stay as they are. This change adds a building block; integrating it into the Warden is a separate, later change.

## Impact

- **New files**:
  - `src/microjail/adapters/lxd_monitor.py` defines `LxdMonitor`, `LifecycleEvent`, `LifecycleMetadata`, and the pure helpers `parse_event` and `matches`.
  - `src/microjail/adapters/executor.py` defines the `CommandExecutor` protocol and the `LocalExecutor` default, moved out of `workshop.py` so the same injection point is shared with `LxdMonitor`.
- **Modified files**:
  - `src/microjail/adapters/workshop.py` now imports `CommandExecutor` and `LocalExecutor` from the new `executor` module instead of defining them.
  - `src/microjail/microjail.py` re-exports `CommandExecutor` from its new location for backward-compatible imports.
- **New tests**: `tests/unit/adapters/__init__.py` and `tests/unit/adapters/test_lxd_monitor.py`. Cover the constructor defaults, event filtering (container + project match), non-matching events being skipped, EOF raising `StopIteration`, `close()` terminating the subprocess and being idempotent, the `CommandExecutor` injection shape, and the context manager calling `close()` on both normal and exceptional exits. No `lxc` binary on `$PATH` required; tests use fake `Popen` and `CommandExecutor` objects.
- **No production callers in this change.** The library is shipped unused; the next change on `refactor/event-warden-retry` (or equivalent) will wire `LxdMonitor` into `Warden`.
- **No new runtime dependencies.** Uses only `subprocess`, `contextlib`, and `msgspec` (already a project dependency), plus `microjail.exceptions.MicrojailError` if/when typed errors are added.
- **No public API breakage for end users.** The `CommandExecutor` symbol is re-exported from `microjail.microjail` under the same name; code that imported it from there continues to work. `workshop.py`'s public surface is unchanged.
- **No CLI surface changes.** `lxc monitor` runs as a child process; its lifecycle is invisible to the user.
