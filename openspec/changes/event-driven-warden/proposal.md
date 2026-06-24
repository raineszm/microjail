## Why

The `Warden` in `src/microjail/warden.py` currently supervises a workload by polling every gate and capability on a fixed interval (default 1s) and terminating on the first violation. Polling has two real costs: (1) the host runs `gate.check()` and `cap.check()` on every tick for the entire workload lifetime, even when nothing has changed, and (2) a device can be added and removed inside a single interval and the Warden never observes the violation — a real-time gap. The LXD daemon already broadcasts these changes as lifecycle events over `lxc monitor`, and the recently-landed `LxdMonitor` (see `openspec/changes/archive/2026-06-23-lxd-event-monitor/`) is the building block for streaming them. The DESIGN.md (`Runtime Enforcement` section) explicitly calls out: *"Polling is the correctness baseline. Event-driven monitoring may be added later as an optimization."* — this change is that optimization.

## What Changes

- **Replace the polling loop in `Warden.supervise()` with an event-driven drain over an `LxdMonitor`.** A matching lifecycle event triggers `check_policies()`; `process.wait(timeout=interval)` still provides the upper bound on tick latency and the exit-code passthrough. The interval parameter is retained as the *fallback poll period* and as the timeout on `process.wait()`.
- **Run a background thread inside `supervise()` that pumps `LxdMonitor` events into a `queue.Queue`.** Without this, `next(monitor)` would block on `readline()` while the workload process has already exited, and the supervision thread would not notice the exit until the next LXD event (or monitor EOF) — a real hang on quiet workloads. The background thread decouples event delivery from `process.wait`, so the supervision thread sees the workload's exit immediately. The `LxdMonitor` API itself is unchanged.
- **Add a `monitor_factory` parameter to `Warden.__init__`.** Type `Callable[[str, str], LxdMonitor] | None`, default `None`. When `None`, the Warden uses the `LxdMonitor` class itself as the factory. The factory is called once, lazily, at the start of `supervise()` with `(microjail.container_name(), microjail.lxd_project())` — never in `__init__` — so the `lxc monitor` subprocess only spawns when supervision actually begins. Tests pass a fake factory (e.g. `lambda c, p: fake_monitor()`) that accepts the strings and ignores them, mirroring the existing `CommandExecutor` injection pattern.
- **Establish a baseline state snapshot before the iterator starts.** The first `lxc monitor` event is a *delta*, not a snapshot. Before opening the monitor, `supervise()` calls `gate.check()` and `cap.check()` once; if any check fails the warden terminates immediately, exactly as it would have on the first polling tick. After the snapshot, the monitor is the source of truth.
- **No new public surface.** The CLI, gate/capability protocols, `MicroJail`, `commands.supervision.supervise_workload`, and the `lxd-event-monitor` and `warden-monitoring` spec contracts are unchanged from the caller's perspective. The behavioral change is "checks happen in response to events instead of on a timer."
- **No new dependencies.** `LxdMonitor` already exists; this change is purely glue.
- **No new exit codes.** A policy violation is still a policy violation; the trigger (poll vs. event) is not part of the contract.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `warden-monitoring`: the polling-interval requirement is replaced with a "checks fire in response to LXD lifecycle events" requirement, with the interval re-scoped to the fallback/upper-bound role. The "terminates on gate violation" / "warns or terminates on capability violation" / "handles normal exit" requirements are unchanged in their observable behavior; only the trigger changes.

## Impact

- **Modified files**:
  - `src/microjail/warden.py`: `Warden.__init__` gains an optional `monitor_factory: Callable[[str, str], LxdMonitor] | None = None` parameter (default `None`, falls back to the `LxdMonitor` class); `supervise()` is rewritten to (1) run a baseline `check_policies()`, (2) construct the monitor via `self.monitor_factory(microjail.container_name(), microjail.lxd_project())`, (3) start a daemon thread that pumps `next(monitor)` into a `queue.Queue` and signals EOF with a `None` sentinel (capturing unexpected exceptions into a `MonitorError` wrapper), and (4) loop on `process.wait(timeout=interval)` + queue drain + `check_policies()`. `check_policies()` is updated to wrap each `gate.check()` and `cap.check()` in try/except and treat exceptions as policy violations, per DESIGN.md line 298. `terminate_workload()` is unchanged.
  - `tests/unit/test_warden.py`: the existing polling tests are replaced with event-driven equivalents; a `FakeLxdMonitor` test helper is introduced (a real blocking iterator with `enter`/`exit`/`deliver`/`close`) and the violation / exit / escalation semantics are tested with `Mock(spec=MicroJail)` and a fake `monitor_factory` returning the fake monitor.
- **No CLI / protocol / workshop / lxc / executor changes.** The `LxdMonitor` injection shape mirrors the existing `CommandExecutor` injection pattern.
- **No migration concerns.** The CLI and end-user experience are unchanged. The `warden-monitoring` spec is updated in-place by the matching delta spec; old behavior is replaced rather than deprecated.
- **No new dependencies.** Only stdlib + the already-shipped `LxdMonitor`.
