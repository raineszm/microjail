## Context

Microjail stores its security policy in `.microjail/config.yaml` on the host. Workshop containers mount the host project directory inside the container, meaning a workload process can reach this file through that mount and overwrite it — altering gates or capabilities while the Warden is running, or poisoning the config for the next `microjail run`.

The existing `lxc` adapter already supports adding and removing named disk devices. LXC disk devices accept a `readonly=true` flag that creates a read-only bind mount at the specified container path, shadowing whatever writable mount covers that path via the parent directory mount.

## Goals / Non-Goals

**Goals:**
- Prevent any process inside the container from writing to the microjail config file.
- Follow the established `check → enforce → release` gate lifecycle.
- Require no new dependencies.
- Include the gate in `Lockdown.default()` so it is active without any user configuration.

**Non-Goals:**
- Protecting the config from host-side modification (out of scope for a container gate).
- Hiding the config contents from the workload (read access is intentionally retained so the agent can inspect its own policy).
- Handling configs that don't yet exist on disk at enforce time (the gate is enforced after `microjail init`, so the file will always exist).

## Decisions

### D1: Check by device presence, not by write probe

`check()` inspects the LXC instance's device list for our named device with `readonly=true` rather than running a write probe inside the container.

**Rationale**: A device-list query is a single `lxc query` call and requires no in-container subprocess. It tests the structural property that `enforce()` establishes, matching how `release()` and `enforce()` operate on the same device list. A write probe would be slower and require the container to be running.

**Rejected alternative**: `workshop.exec_` write probe — heavier, container must be fully running, and tests an effect rather than the cause.

### D2: Container-side config path is a known constant

The config file is always accessible inside the container at `/project/.microjail/config.yaml`. Workshop unconditionally mounts the host project directory at `/project` in every container it manages.

**Rationale**: A fixed, well-known path is simpler, faster, and has no failure mode from a missing device. There is no need to walk the device list to discover the mount point at runtime.

**Rejected alternative**: Discovering the container-side path by walking instance devices and matching `source == str(project_path)` — unnecessary complexity given the guaranteed mount convention.

### D3: Fixed LXC device name `"microjail-config-ro"`

The LXC device name is a fixed constant rather than derived from the microjail name.

**Rationale**: Device names are scoped to a single container. No two microjails share a container, so collisions are impossible. A fixed name makes `check()` and `release()` simple dictionary lookups.

### D4: Gate included in default lockdown

`ReadonlyConfig` is appended to `Lockdown.default()` so the config is always protected without requiring user opt-in.

**Rationale**: The default lockdown is the "secure-by-default" configuration (see DESIGN.md §Secure Defaults). Config self-mutation is a fundamental attack vector that should be closed automatically.

## Risks / Trade-offs

- **LXC bind-mount target must exist**: If the config file path does not exist in the container's namespace at enforce time (e.g., the container was launched before `microjail init`), `lxc config device add` will fail. This is an expected and detectable error — the config file must exist on the host for microjail to have been initialised at all.
- **Device add on running container**: LXC supports hot-adding disk devices to running containers. This is an existing precedent established by `NetworkDrop.enforce()` (which hot-removes NICs), so it is already proven to work in this project's deployment.
- **Shadowing only the exact path**: The read-only bind mount covers only `config.yaml`, not the `.microjail/` directory. A workload could still create other files under `.microjail/`. This is intentional — we protect only the file that contains the policy.

## Test Strategy

Unit tests mock `lxc` and `workshop` adapters to verify `check`/`enforce`/`release` call contracts without a live container.

The functional test (`tests/functional/gates/test_readonly_config.py`) uses an actual workshop container and a `workshop.exec_` write probe against `/project/.microjail/config.yaml` to confirm the bind mount is enforced end-to-end. A write probe is appropriate here — unlike in `check()`, the functional test is validating observable behaviour rather than structural state, and the container is guaranteed to be running.
