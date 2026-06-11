# microjail

**Orchestrate a network-sealed, policy-enforced execution environment for autonomous agents and other untrusted workloads.**

`microjail` sits on top of [Canonical Workshop](https://canonical.com/blog/introducing-workshop-sandboxed-development-environments) and [LXD](https://canonical.com/lxd). It does not implement sandboxing or proxying itself — Workshop and LXD handle the containment. What `microjail` adds is a declarative security policy (a **Lockdown**), lifecycle management for applying and releasing it, and continuous runtime enforcement while a workload runs.

Built for running AI coding agents in a controlled environment. Let an agent loose on a codebase; with network egress removed and policy continuously enforced, it cannot phone home, exfiltrate code, or reach services you have not explicitly authorised. But any workload you would rather run without a route off the box fits the same model.

______________________________________________________________________

## Goals

- Secure-by-default execution: no capabilities granted unless explicitly declared.
- Explicit authorisation: every network path and mount is a named, declared capability.
- Continuous enforcement: a Warden monitors policy invariants throughout execution and terminates the workload on violation.
- Crash-resistant stateless safety: no runtime state is persisted; every check reads live system state, so a crash or manual intervention leaves no stale "locked" flags.
- Simple CLI workflow that composes naturally with Workshop.

## Non-goals

- `microjail` is **not an escape-prevention mechanism**. It stops a workload from reaching the network and enforces declared restrictions. It is not a hardened defence against a workload actively trying to break out of the LXD container.
- `microjail` does not implement any sandbox or proxy primitive. The container is a Workshop/LXD concern.
- `microjail` is not a substitute for choosing what you run. Policy enforcement is only as good as the policy you declare.

______________________________________________________________________

## Prerequisites

- Ubuntu with [Workshop](https://ubuntu.com/workshop/docs/) and LXD 6 installed:
  ```bash
  sudo snap refresh lxd --channel=6/stable || sudo snap install lxd --channel=6/stable
  sudo snap install workshop --classic
  ```
- Python 3.14+ (required by microjail itself)
- [`uv`](https://docs.astral.sh/uv/) for installation

______________________________________________________________________

## Installation

```bash
uv tool install microjail
```

Or, to install into an existing project environment:

```bash
uv add microjail
```

______________________________________________________________________

## Usage

A microjail session has four commands.

### `microjail init`

Create a microjail for the current project directory. This initialises a Workshop environment and writes a `.microjail/config.yaml` with the default Lockdown (network-egress gate, read-only config mount, no capabilities).

```bash
cd ~/my-project
microjail init my-project
```

To bring an existing Workshop project under microjail management:

```bash
microjail init my-project --adopt
```

#### `--sdks`

Pass additional Workshop SDKs as a comma-separated list. The `direnv` SDK is always included by default.

```bash
microjail init my-project --sdks golang,java
```

#### `--base`

Specify a Workshop base image (defaults to Workshop's own default if omitted).

```bash
microjail init my-project --base ubuntu@22.04
```

#### `--project` / `-p`

Run the command against a specific project directory instead of the current working directory. Accepted on all commands.

```bash
microjail --project /path/to/project init my-project
microjail --project /path/to/project lock
microjail --project /path/to/project unlock
```

### `microjail lock`

Apply the configured Lockdown without running a workload. Capabilities are provisioned first; gates are enforced second. Use this to verify the environment is sealed before doing anything else, or to reach the safest reachable posture after a partial failure.

```bash
microjail lock
```

### `microjail run`

Apply the Lockdown and run a workload inside the Workshop environment under Warden supervision. The workload only starts if the full Lockdown is successfully applied. The Warden monitors policy continuously and terminates the workload on any gate or (if configured) capability violation. The environment is not unlocked when the workload exits.

```bash
microjail run -- opencode run "refactor the parser module"
```

Workload exit codes are passed through. If microjail itself fails before or during execution, a bitmask exit code in the `0x40` range is returned instead (see *Exit codes* below).

### `microjail unlock`

Explicitly release the Lockdown — terminate any supervised workload, release gates, revoke capabilities. This is the only command that weakens the policy.

```bash
microjail unlock
```

### Full example

```bash
cd ~/my-project

# Initialise a microjail for this project
microjail init my-project

# Run the workload; lock is applied automatically before launch
microjail run -- opencode run "add docstrings to src/"

# Release when you're done
microjail unlock
```

______________________________________________________________________

## Wiring up network access

By default the Lockdown grants **zero capabilities**: no network paths are open. To give a workload access to a specific host service — an inference endpoint, an MCP server, a GitHub proxy — declare an endpoint capability:

```yaml
# .microjail/config.yaml
lockdown:
  caps:
    - type: endpoint-tunnel
      name: inference
      endpoint: localhost:8080
  gates:
    - type: network-egress
    - type: readonly-config
```

An endpoint capability provisions a Workshop tunnel that forwards the named `host:port` into the container at the same address. Only declared capabilities produce authorised network paths; pre-existing Workshop tunnels not represented in the Lockdown are treated as unauthorised and must be removed before the network-egress gate will enforce.

> **Workshop adoption note:** If you bring an existing Workshop project under microjail management with `--adopt`, you must declare any tunnels or connections you want to keep as endpoint capabilities. Anything not declared becomes unauthorised.

______________________________________________________________________

## How the Lockdown works

A **Lockdown** is declarative policy: a list of **Capabilities** and a list of **Gates**. It describes what should be available and what must be restricted — not whether the environment is currently locked.

**Applying** a Lockdown follows a two-phase sequence:

1. **Capabilities first** — each capability is checked and provisioned if absent, then verified. Failures are collected; by default they block workload launch.
1. **Gates second** — each gate is checked and enforced if unsatisfied, then verified. The first gate failure stops enforcement.

Ordering matters: authorised access is established before broad denial policies are applied.

**Releasing** a Lockdown reverses this: gates release in reverse order, then capabilities are revoked in reverse order. Release is always explicit — there is no automatic unlock.

**Stateless safety** — no runtime state is persisted. `microjail lock` does not read a cached flag; it runs `gate.check()` and `capability.check()` against live system state. This makes the tool crash-resistant and safe after manual intervention or Workshop modifications.

### Implemented gates

| Gate | What it enforces |
|---|---|
| `network-egress` | Removes all NIC devices from the LXD container. Egress is verified unreachable before the workload starts. Workshop tunnels continue to work after NIC removal. |
| `readonly-config` | Mounts the `.microjail` config directory into the container read-only. The workload cannot modify its own policy. |

### Exit codes

Microjail uses a bitmask scheme so callers can distinguish policy failures from workload failures:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic command/config/Workshop error |
| `66` | Capability application failure |
| `68` | Gate application failure |
| `82` | Fatal runtime capability policy violation |
| `84` | Runtime gate policy violation |
| `98` | Capability release failure |
| `100` | Gate release failure |

If the workload ran and no fatal policy issue occurred, its own exit code is passed through unchanged.

______________________________________________________________________

## Technical summary

`microjail` is a Python 3.14 CLI built with [Typer](https://typer.tiangolo.com/), [msgspec](https://jcristharif.com/msgspec/), and [Rich](https://rich.readthedocs.io/). It uses `workshop` and `lxc` as subprocesses; it does not link against any LXD or Workshop library directly.

The configuration file is `.microjail/config.yaml`, serialised with msgspec. No runtime state is written to disk.

The Warden polls policy at a configurable interval (default: 1 second). Gate violations are always fatal. Capability violations are warnings by default and can be promoted to fatal per-capability in config.

```
.microjail/
  config.yaml       # persisted Lockdown declaration
```

______________________________________________________________________

## Developer getting started

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/raineszm/microjail
cd microjail
uv sync
```

**Run the tests:**

```bash
uv run pytest            # fast unit and functional tests
uv run pytest --slow     # all tests, including container-based e2e tests
```

Slow tests require `lxc` and `workshop` on `PATH`. Tests marked `lxd` and `workshop` are skipped automatically when those binaries are absent.

**Lint and type-check:**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check src
```

### Project layout

```
src/microjail/
  cli.py              # Typer app; registers commands
  microjail.py        # MicroJail config struct and core operations
  lockdown.py         # Lockdown, CapabilityError, GateError
  commands/           # init, lock, run, unlock
  gates/              # Gate implementations (NetworkDrop, ReadonlyConfig)
  caps/               # Capability protocol and implementations
  adapters/           # Thin wrappers over lxc and workshop CLIs
tests/
  unit/               # Pure logic, no subprocesses
  functional/         # Adapter and command tests with mock Workshop/LXD
  e2e/                # Full container-based workflow tests (--slow)
```

______________________________________________________________________

## Status

Early development. The CLI, configuration schema, and gate set will change.

**Currently implemented:**

- `init`, `lock`, `run`, `unlock` commands
- `network-egress` gate (LXD NIC removal + egress probe)
- `readonly-config` gate (read-only config mount)
- Stateless Lockdown apply/release lifecycle

**Planned:**

- Endpoint capabilities (Workshop tunnel provisioning for declared host services)
- Warden runtime monitoring loop
- `destroy` command (stop workload + release Lockdown + remove Workshop environment)
- Expanded gate set (filesystem-mode assertions, Linux capability drops)
- Snap packaging

______________________________________________________________________

## Warnings

- **The workflow is the boundary.** Start a workload outside `microjail run` and the Warden is not watching. Run it through the gates or the guarantees do not apply.
- **Egress control, not escape prevention.** `microjail` removes network access and enforces declared restrictions. It is not a defence against a workload trying to break out of the LXD container.
- **Declare everything.** Pre-existing Workshop tunnels or connections not represented in the Lockdown are unauthorised. If they must be removed to enforce the network-egress gate, `microjail` requires explicit confirmation (`--force`). Without it, gate enforcement fails.
