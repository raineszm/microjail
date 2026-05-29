# microjail

**Ephemeral, network-sealed environments for running workloads you don't fully trust.**

`microjail` wraps [Canonical Workshop](https://canonical.com/blog/introducing-workshop-sandboxed-development-environments) to give you a sandbox you can set up, fill with whatever you need, and then **lock** — cutting network egress — before running a workload inside it. When the run finishes, you **unlock** it and networking comes back.

It's built for cases where you want a workload to do its thing without being able to reach the outside world. Running [autonomous coding agents](https://opencode.ai) is one such case we have in mind — let an agent loose on a workspace and it can't phone home if there's no network to phone over — but it's not the only one. Anything you'd rather run with no route off the box fits: untrusted scripts, build steps, that one dependency you don't trust.

---

## How it works

A `microjail` session has three phases:

1. **`init`** — Create a Workshop environment, declaring intent up front (e.g. local inference, an agent harness). This decides what gets provisioned and which passthroughs are wired in.
2. **Provision** — Install packages and set up the workspace through thin wrappers (`apt`, `uv`, and so on). Everything lands in the container or the mounted workspace.
3. **`run`** — Lock the environment and execute the workload. Before the process starts, `microjail` runs a set of checks (see [gates](#lock-gates)); the command only spawns if they all pass.

While locked, the workload keeps full filesystem access — including the workspace [Workshop](https://canonical.com/blog/introducing-workshop-sandboxed-development-environments) bind-mounts in — but has no network egress. After the run you unlock to provision again or tear down.

Workshop does the actual containment: each environment runs in an unprivileged [LXD](https://canonical.com/lxd) system container. `microjail` adds the lifecycle and the lock/unlock egress control on top.

---

## Usage

> Commands below are illustrative; the CLI is still settling.

```bash
# 1. Create an environment, declaring intent
microjail init myproject --inference llama-cpp --agent opencode

# 2. Provision it
microjail apt install ripgrep
microjail uv install httpx feedparser

# 3. Lock and run a workload
microjail run -- opencode run "refactor the parser module"

# 4. Unlock when you're done
microjail unlock
```

### Lock gates

`microjail run` won't start your command until it has confirmed, at minimum:

- **Egress is actually down** — the network path is severed and verified unreachable, not just asked to go away.
- **Inference socket is present and reachable** (when local inference is enabled) — so the workload has a model before the network disappears.
- **Workspace is mounted as expected** — what you provisioned is what the workload sees.

That's the floor. More gates (leftover-interface detection, filesystem-mode checks, resource caps) will follow as things harden.

---

## Local inference passthrough

One thing `microjail` wires up for you: running an agent against a **local model**, so no inference traffic needs to leave the machine in the first place.

- Run [llama.cpp](https://github.com/ggml-org/llama.cpp) on the host, exposing a [Unix domain socket](https://en.wikipedia.org/wiki/Unix_domain_socket).
- Workshop bind-mounts the workspace folder into the container by default, so dropping the socket there makes it visible inside the sandbox with no extra plumbing. (Workshop SDKs can also expose it directly.)
- `microjail` writes the [OpenCode](https://opencode.ai) config (`opencode.json` in the workspace) to point the agent at that socket.

End result: an agent running inside a locked container, served by a model on the host, with nothing reaching out.

---

## Warnings

- **The workflow is the boundary.** `microjail` is only as safe as the path it defines. Side-load into the container or start the workload outside `microjail run` and the guarantees are gone. Run it through the gates or don't run it.
- **This is egress control, not escape prevention.** It stops a workload from reaching the network. It is not a defense against something actively trying to break out of the container. Pick your threat model accordingly.
- **Local inference is the point.** Aim a locked agent at a remote API and you've undone the whole exercise.
- **Early days.** The CLI, flags, and gate set will change.

---

## Roadmap

**Phase 1 — Core lifecycle**
- `init` with intent flags (local inference, agent harness)
- Provisioning wrappers (`apt`, `uv`, virtualenvs)
- `run` with lock + baseline gates
- `unlock` to restore networking
- llama.cpp <-> OpenCode socket passthrough and `opencode.json` generation

**Phase 2 — Visibility**
- Environment status / inspection
- Run logging — a record of what actually executed
- Expanded gate set (interface enumeration, filesystem-mode assertions)

**Phase 3 — Hardening**
- Resource limits (cgroups)
- More inference backends and agent harnesses
- Ship as a [snap](https://snapcraft.io)

---

## Status

Currently a **Python tool**. A snap is planned, which would line it up with the rest of the `micro*` family ([microstack](https://snapcraft.io/microstack), [microceph](https://snapcraft.io/microceph), [microk8s](https://microk8s.io)) and give confined, reproducible installs.

**Prerequisites:** Workshop and a recent LXD — see the [Workshop announcement](https://canonical.com/blog/introducing-workshop-sandboxed-development-environments) to get set up.
