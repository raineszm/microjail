## Context

The `Warden` in `src/microjail/warden.py` supervises a workload by polling each gate and capability on a fixed interval (default 1s) and terminating the workload on the first violation. Polling is a poor fit for changes the LXD daemon already broadcasts as lifecycle events (start, stop, device added/removed, config updated). A polling-based Warden also has a real-time gap: a device could be added and removed in a single polling interval and the Warden would never see it.

The `refactor/event-warden-retry` branch exists to replace polling with an event-driven Warden, but it needs a reliable primitive for streaming LXD events for a single container. The codebase has no such primitive today: `src/microjail/adapters/lxc.py` is a thin wrapper over one-shot `lxc` commands (`query`, `network attach`, `device add/remove`, `stop`), and `src/microjail/adapters/workshop.py` does not touch LXD directly. A previous WebSocket-based attempt left a stale `lxd_events.cpython-314.pyc` in `__pycache__` but no source file; that approach is abandoned and out of scope.

This change adds a single new module, `src/microjail/adapters/lxd_monitor.py`, that owns a long-lived `lxc monitor` subprocess and exposes a Pythonic, thread-safe interface to its events. The Warden (or any future caller) consumes the queue. The change is deliberately library-only: no caller in this change wires `LxdMonitor` into anything.

## Goals / Non-Goals

**Goals:**
- Provide a thread-safe subscription to LXD lifecycle events for one `(container, project)` pair.
- Filter producer-side so the queue only ever contains events the configured caller cares about.
- Be fully unit-testable without a real LXD daemon or a real `lxc` binary.
- Behave predictably on failure: subprocess death, malformed JSON, and container-not-found all produce well-defined states, not exceptions bubbling up at random times.
- Match the existing codebase's style: stdlib-only, `subprocess`/`Popen`-based, no asyncio, no new runtime dependencies.

**Non-Goals:**
- Reconnect / retry on subscription loss. The monitor reports the failure via `last_exception`; a higher layer (the future event-driven Warden) decides whether to relaunch.
- Interpreting events. The monitor does not translate lifecycle actions into gate/cap violations; it only delivers JSON events.
- Replacing the existing `Warden.supervise()` polling loop. The Warden is unchanged in this change.
- Reading non-lifecycle event types (logging, operation, etc.). Only `type: lifecycle` is delivered.
- A public CLI surface. `lxc monitor` runs as a child process; the user never sees it.

## Decisions

### Decision 1: Use `lxc monitor` as a child process, not the LXD WebSocket API directly
- **Rationale**: The rest of `microjail` already shells out to the `lxc` client (`src/microjail/adapters/lxc.py` uses `lxc query`, `lxc network attach`, `lxc config device …`). `lxc monitor` is the canonical client and inherits the host's LXD credentials and project scoping for free. Direct WebSocket access would require us to reimplement cert handling, project query parameters, reconnection, and binary framing, and would pull in a runtime dependency (`websockets`) that is not currently in `pyproject.toml`.
- **Sub-decision: Use `--format=json` and parse with `msgspec.json.decode`.** `lxc monitor` defaults to YAML, but YAML from this command is a multi-document stream separated by `---`. `msgspec.yaml.decode` only decodes a single document; the multi-document stream would require us to split on `---` ourselves or reach for `pyyaml.parse_all()`, at which point the msgspec integration is doing very little work. `--format=json` emits one complete JSON object per line, which `msgspec.json.decode` (already used in `lxc.py`) decodes trivially per line. Both formats carry identical data and the same nanosecond-precision RFC3339 timestamp, so JSON costs us nothing in fidelity. The command we spawn is therefore:
  ```
  lxc monitor --project=<project> --type=lifecycle --format=json
  ```
- **Alternatives Considered**:
  - **WebSocket via `websockets.sync.client`**: tried on the (now-orphaned) `lxd_events` module, no source committed. Rejected for the dependency and credential-management reasons above; also because the rest of the codebase uses the `lxc` client and consistency is worth a small overhead per event line.
  - **`lxc monitor` over a streaming REST endpoint**: LXD does not expose lifecycle events via REST; this is a non-option.
  - **`--format=yaml` with `msgspec.yaml.decode`**: rejected because YAML output is multi-document (`---` separated) and `msgspec.yaml.decode` does not parse multi-document streams natively. Identical data to JSON; no upside to justify the parsing complexity.
  - **`--format=pretty`**: rejected — human-readable `key=value` form, not machine-parseable, and truncates timestamps to second precision.

### Decision 2: Reader thread + `queue.Queue`, not asyncio or callback registration
- **Rationale**: The codebase is synchronous. The blocking call (`process.stdout.readline()`) maps cleanly onto a daemon thread, and `queue.Queue` is the standard, well-understood synchronization primitive. `asyncio` would force the rest of the codebase (which uses `subprocess.Popen` everywhere) to grow an event loop, and a callback API would be harder to test and reason about than a polled queue.
- **Alternatives Considered**:
  - **`asyncio.create_subprocess_exec`**: rejected to keep the rest of the codebase free of an event loop.
  - **Push-based callbacks (`on_event(event)`)**: rejected because (a) testing callbacks requires mocks-with-mocks, and (b) the future Warden wants to drain events on its own supervision loop, which is itself a polling loop, so a queue is the natural fit.

### Decision 3: Filter on the producer side, not the consumer side
- **Rationale**: An LXD host under any load produces many events per second across all instances and all event types. Pushing every event to the queue and filtering on `events()` would let unrelated events starve the queue and the per-event overhead would compound. Filtering inside the reader thread (after JSON parse, before `queue.put`) keeps the queue size bounded to "events for this monitor's container".
- **Alternatives Considered**:
  - **Consumer-side filtering**: rejected for the memory and CPU reasons above, and because it forces every caller to re-implement the same filter logic.
  - **`lxc monitor --type=…` server-side filtering**: where supported (e.g. `--type=lifecycle`), use it; the per-event filter is the safety net for hosts that do not support granular filters.

### Decision 4: Inject the subprocess launcher via a `MonitorLauncher` protocol
- **Rationale**: `src/microjail/adapters/workshop.py` already defines a `CommandExecutor` protocol with `run`/`popen` and a `LocalExecutor` default. We follow the same pattern: `LxdMonitor.__init__` takes an optional `launcher: MonitorLauncher` parameter that defaults to a thin wrapper around `subprocess.Popen`. Tests substitute a fake launcher that returns a fake `Popen` whose `stdout` is an iterable of preset lines, and whose `wait()`/`terminate()`/`kill()` are no-ops or controlled by the test.
- **Alternatives Considered**:
  - **Mock `subprocess.Popen` directly**: rejected because it is brittle (every call site in the test has to patch `subprocess.Popen`), and a real `subprocess.Popen` on a process that writes to a temp file is harder to control than a plain iterable.
  - **Use `LocalExecutor` from `workshop.py`**: rejected as scope creep; `MonitorLauncher` is the single method we need (`Popen`-shaped), and reusing `LocalExecutor` would couple `LxdMonitor` to `workshop.py`'s executor for no benefit.

### Decision 5: `stop()` terminates the subprocess; reader thread exits on closed pipe
- **Rationale**: `Popen.stdout.readline()` returns `""` on EOF, so the reader thread's main loop naturally exits when the subprocess is terminated and its stdout pipe is closed. `stop()` calls `process.terminate()`, then `process.wait(timeout=stop_timeout)`, then escalates to `process.kill()` if the timeout elapses, then `join()`s the reader thread. No `Event`/flag is needed to wake the reader; closing the pipe is enough.
- **Alternatives Considered**:
  - **`threading.Event` flag checked on every readline**: rejected as redundant — `readline()` already returns on EOF, and adding a flag doubles the code paths through the reader loop.
  - **Polling `is_alive()` from the reader thread**: rejected because `readline()` already blocks on the pipe, which is more efficient and simpler than polling.

### Decision 6: No reconnect, ever, in this change
- **Rationale**: The user explicitly scoped this change to "creating the functionality to monitor lxd events and we'll worry about using it later". Reconnect policy is a caller decision (the future Warden may want to escalate on `last_exception` rather than retry). The monitor surfaces the failure state and exits; the caller decides what to do.
- **Alternatives Considered**:
  - **In-process exponential backoff reconnect**: rejected as scope creep; a different change can add a `LxdMonitorSession` wrapper that wraps `LxdMonitor` and adds a reconnect policy, if that turns out to be what the Warden wants.

## Event Schema

`lxc monitor --type=lifecycle --format=json` emits one JSON object per line. Each object has a fixed set of top-level fields; the `metadata` sub-object carries the action, source, and (usually) the resource name and project. The monitor only needs a small subset of these fields to do its job: filter by event type, match the configured container, and match the configured project. We model only what we need; the rest is silently ignored by `msgspec` (it does not reject unknown fields by default).

### Filter-driving fields (required by the schema)

| Field | Type | Source | Used for |
|---|---|---|---|
| `type` | `str` | top-level | Filter — must equal `"lifecycle"`. Defense in depth on top of `--type=lifecycle`. |
| `project` | `str` | top-level | Filter — must equal the configured LXD project. |
| `metadata.action` | `str` | nested | Recorded on the event for the consumer (e.g. `instance-created`, `instance-started`). Not used for filtering. |
| `metadata.source` | `str` | nested | Filter — must end with `/1.0/instances/<container_name>`. |

### Pass-through fields (kept, not used for filtering)

| Field | Type | Source | Notes |
|---|---|---|---|
| `timestamp` | `str` | top-level | RFC3339 with nanosecond precision, e.g. `2026-06-23T12:48:45.785189155-05:00`. Kept as `str`; parsing to `datetime` is deferred to consumers that need ordering or comparison. |
| `location` | `str` | top-level | Always present. `"none"` on a non-clustered LXD; cluster member name otherwise. Always accepted as a string. |
| `metadata.name` | `str \| None` | nested | Usually present on instance events; the container name as a separate field from `source`. Optional because not every lifecycle event carries it. |
| `metadata.project` | `str \| None` | nested | Usually duplicates the top-level `project`. Kept for cross-checking; the top-level field is authoritative for filtering. |
| `metadata.context` | `dict \| None` | nested | Varies by action (e.g. `{"location": "none", "storage-pool": "default", "type": "container"}` on `instance-created`). Untyped dict; consumers that care can inspect it. |
| `metadata.requestor` | `dict \| None` | nested | Present on user-triggered actions (e.g. `instance-started` from `lxc start`). Carries `address`, `protocol`, `username`. Untyped dict. |

### Fields intentionally NOT modeled

- **Top-level fields** other than `type`, `timestamp`, `location`, `project`, `metadata`: there are none on lifecycle events in the LXD versions we tested. If a future LXD adds a new top-level field, msgspec silently ignores it.
- **`metadata.context.*` and `metadata.requestor.*` sub-fields**: not modeled as a `msgspec.Struct` because their shape varies by action and the monitor does not need to inspect them. Kept as `dict` so the data is not lost.
- **Non-lifecycle event types** (logging, operation): not subscribed to (`--type=lifecycle` on the command line) and not modeled. The struct only sees lifecycle-shaped JSON.

### msgspec struct definition

```python
import msgspec


class LifecycleMetadata(msgspec.Struct, frozen=True):
    """Action + resource identification for one LXD lifecycle event."""

    action: str
    source: str
    name: str | None = None
    project: str | None = None
    context: dict | None = None
    requestor: dict | None = None


class LifecycleEvent(msgspec.Struct, frozen=True):
    """One LXD lifecycle event, parsed from one line of `lxc monitor --format=json`."""

    type: str
    timestamp: str
    location: str
    project: str
    metadata: LifecycleMetadata
```

The filter inside the reader thread is a pure function on `LifecycleEvent`:

```python
INSTANCE_PREFIX = "/1.0/instances/"

def matches(event: LifecycleEvent, container_name: str, lxd_project: str) -> bool:
    if event.type != "lifecycle":
        return False
    if event.project != lxd_project:
        return False
    if not event.metadata.source.startswith(INSTANCE_PREFIX):
        return False
    # source is "/1.0/instances/<name>"; tolerate query strings or trailing segments
    # by splitting on "/" and taking the segment after the prefix.
    return event.metadata.source.split("/")[3] == container_name
```

(`split("/")[3]` is intentional: index 0 is empty for a leading-slash path, index 1 is `1.0`, index 2 is `instances`, index 3 is the name. A naive `endswith(container_name)` would let `evil-name-foo` match container `name`.)

## Risks / Trade-offs

- **[Risk] A burst of LXD events between `start()` and the first `events(timeout)` call accumulates in the queue.** The reader thread runs at line-read speed, which is effectively the same speed the producer runs, so the queue depth is bounded by "events delivered since the last consumer read". The future Warden is a single consumer on a fixed interval; queue depth in steady state is `events_per_interval * filter_rate`. → *Mitigation*: producer-side filtering keeps the queue small. If the future Warden shows the queue growing unboundedly in practice, the Warden can call `events(timeout=0)` to drain without blocking.
- **[Risk] Subprocess death on a transient LXD hiccup leaves the monitor permanently down.** This is intentional per Decision 6, but it means the caller (Warden) must be ready to detect `last_exception` and decide. → *Mitigation*: `last_exception` is checked in the `events(timeout=0)` polling pattern the future Warden will use; escalation is the Warden's job, and the spec requires `events()` to keep returning `None` after subscription loss so the caller has a stable state to observe.
- **[Risk] `lxc monitor` JSON line format changes between LXD versions.** Different LXD versions may emit slightly different keys, or wrap metadata differently for older events. → *Mitigation*: `msgspec.Struct` (not `strict=True`) silently ignores extra fields, so new top-level or `metadata.*` keys added by a future LXD do not break parsing. The filter-driving fields (`type`, top-level `project`, `metadata.source`) are all documented as always present on lifecycle events across LXD 5.x; if any one is missing or renamed, msgspec raises `msgspec.ValidationError` and the line is dropped (malformed-JSON path). The spec already requires malformed lines to be dropped without crashing.
- **[Risk] `lxc monitor` does not emit synthetic events for resources that already exist when the subprocess starts.** If a workload container is already running when the monitor is constructed, the first event the monitor will see is the *next* transition, not a snapshot of the current state. → *Mitigation*: out of scope for this change. The future Warden-integration change is responsible for establishing baseline state (via `lxc list` / `lxc query` before the monitor starts) and treating the first event as a delta from that baseline. Documented here so the integration change does not assume "the monitor tells you the current state."
- **[Risk] The `project` field appears at both the top level and inside `metadata`, and they should be consistent but LXD does not formally promise they are.** In testing they always agreed, but a future LXD or a clustered deployment could in principle emit an event where they disagree. → *Mitigation*: the filter uses the top-level `project` field as authoritative. The `metadata.project` field is kept on the struct for cross-checking by consumers but is not used for filtering. If the two disagree, the monitor does not raise — it filters by the top-level value and lets the consumer inspect the discrepancy if it cares.
- **[Risk] Reader thread leaks if `start()` is called but `stop()` is never called.** → *Mitigation*: the reader is started with `daemon=True` so it dies with the process; `stop()` is the explicit cleanup path. The spec requires `stop()` to be callable and effective.

## Migration Plan

This change is purely additive: a new module, a new test file, no changes to any existing code, CLI, or spec. Deployment is "merge the branch and ship". Rollback is "revert the merge commit"; no data migration, no schema change, no flag.

When the follow-up change wires `LxdMonitor` into the Warden, that change will:
1. Construct an `LxdMonitor` after `ensure_lockdown` succeeds and before `Warden.supervise()` is called.
2. Pass the monitor's `events(timeout=0)` into the Warden's existing periodic-check path (or replace that path with an event-driven one — that is a separate design decision for the follow-up).
3. Treat `monitor.last_exception` as a fatal enforcement loss (exit code 84 or new code, TBD by that change's design).

None of that is in scope here.

## Open Questions

- **None for this change.** The interface, the error model, and the testability story are settled by the proposal and the spec. The follow-up Warden-integration change will need to decide:
  - Whether to drain `events(timeout=0)` inside the existing `Warden.supervise()` poll, or to replace the poll with a blocking `events(timeout=interval)` and drop the explicit `process.wait(timeout=interval)` step.
  - What exit code to use for `last_exception`-driven enforcement loss. The current `warden-monitoring` spec uses 84 for gate violations and 82 for capability violations; an LXD-event-stream loss is closer to "we lost the ability to enforce at all" and may warrant its own code.
  These are decisions for that change, not this one.
