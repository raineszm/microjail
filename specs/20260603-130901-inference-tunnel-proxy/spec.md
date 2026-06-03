# Feature Specification: Inference Tunnel Proxy

**Feature Branch**: `20260603-130901-inference-tunnel-proxy`

**Created**: 2026-06-03

**Status**: Draft

**Input**: User description: "We're pivoted to no longer use a UNIX domain socket for local inference. Instead what we'll do is use Workshop's tunnel interface to proxy the TCP endpoint. We'll do this by injecting a slot into the system-sdk of the workshop and creating a project SDK with a corresponding plug."

## Clarifications

### Session 2026-06-03

- Q: Should the project SDK for inference be a new named SDK or reuse an existing one?
  → A: A new SDK entry named after the inference provider (e.g., `llama-cpp` for `--inference llama-cpp`) is created alongside `opencode` and `skills`. The slot on the system SDK and the plug on the project SDK are also named after the provider (e.g., `llama-cpp`).

- Q: Does the `opencode.jsonc` `baseURL` change now that the endpoint arrives via tunnel?
  → A: The `baseURL` inside `opencode.jsonc` remains an HTTP URL (`http://localhost:8080/v1` for the default llama-cpp configuration). The difference is that the endpoint is now proxied by Workshop's tunnel rather than arriving via a bind-mounted UDS socket file. The URL does not change; how it becomes reachable changes.

- Q: How does the inference gate verify reachability now that there is no UDS socket file?
  → A: The gate checks that the host-side TCP port (e.g., `localhost:8080`) is accepting connections before the workload starts. This replaces the UDS socket-file existence check. The gate uses the host-side endpoint for verification because Workshop's tunnel is only established after launch.

- Q: How does the Workshop tunnel coexist with the lock mechanism that removes all network interfaces?
  → A: `lock_egress` enumerates ALL LXD devices whose type contains "nic" and clears their external routes (`ipv4.routes.external`, `ipv6.routes.external`). The Workshop tunnel is a separate LXD device (not a NIC-type device) created by `workshop launch`; it is not in the NIC enumeration and survives the lock operation untouched.
- Q: Does the system SDK need both `plugs` and `slots`, or only `slots`?
  → A: Only `slots` on the system SDK; only `plugs` on the project SDK. The system SDK provides the endpoint (a slot), and the project SDK consumes it (a plug). The example `workshop.yaml` in `tmp/` that showed both `plugs` and `slots` on the system SDK was incorrect.

## User Scenarios & Testing *(mandatory)*

A developer initialises a microjail environment with `--inference llama-cpp` and `--agent opencode`. The generated `workshop.yaml` includes a system SDK with a tunnel slot exposing the host's inference endpoint, and a project SDK with a plug that connects to that slot. When the workload runs inside the locked container, the agent can reach the local model at `localhost:8080` — not because a socket file was bind-mounted, but because Workshop's tunnel proxies the TCP connection from host to container.

**Why this priority**: This is the core architectural change. Every other scenario depends on this mechanism working correctly. The entire inference passthrough pivots from filesystem bind-mount to Workshop's tunnel interface.

**Independent Test**: Run `microjail init myproject --inference llama-cpp --agent opencode`; verify the generated `workshop.yaml` contains a system SDK entry with a slot declaring the tunnel interface and a project SDK entry with a plug referencing that slot; verify `opencode.jsonc` points at `http://localhost:8080/v1`; verify that Workshop accepts the definition and creates the environment successfully.

**Acceptance Scenarios**:

1. **Given** `--inference llama-cpp` is specified, **When** `microjail init` generates `workshop.yaml`, **Then** the YAML includes a system SDK entry with a `slots` section that declares a tunnel-slot for the inference endpoint and a project SDK entry with a `plugs` section declaring a corresponding tunnel-plug that connects to that slot.

2. **Given** `--inference llama-cpp` is NOT specified, **When** `microjail init` generates `workshop.yaml`, **Then** no system SDK entry is included, no project inference SDK entry is included, and no tunnel slots or plugs appear in the file.

3. **Given** `--inference llama-cpp` and `--agent opencode` are both specified, **When** `workshop.yaml` is written, **Then** the file contains three SDK entries: `opencode`, `skills`, and the inference project SDK, plus the system SDK with its tunnel slot.

---

### User Story 2 - Inference gate checks host-side TCP port, not UDS socket (Priority: P1)

A developer has initialised with `--inference llama-cpp` and runs `microjail run`. The inference gate verifies that the host-side inference endpoint (e.g., `localhost:8080`) is accepting TCP connections before the workload starts. If the port is not reachable, the gate fails and the workload is never spawned. If it is reachable, the workload proceeds.

**Why this priority**: This is the second half of the pivot. The gate must verify the right thing — not a filesystem path, but a TCP port. Without this change the workload could start without a reachable model.

**Independent Test**: Initialise with `--inference llama-cpp`; without running llama-server, run `microjail run -- echo hello`; verify the command exits non-zero naming the unreachable inference endpoint. Then start llama-server on port 8080 and verify the gate passes.

**Acceptance Scenarios**:

1. **Given** `--inference llama-cpp` was set at init and the host-side TCP port (e.g., `localhost:8080`) is accepting connections, **When** `microjail run` evaluates the inference gate, **Then** the gate passes and the workload proceeds.

2. **Given** `--inference llama-cpp` was set at init but the host-side TCP port is not accepting connections (no server listening), **When** `microjail run` evaluates the inference gate, **Then** the gate fails with a message naming the unreachable endpoint and port.

3. **Given** no `--inference` flag was set at init, **When** `microjail run` evaluates gates, **Then** the inference gate is skipped entirely, regardless of whether a port is listening.

---

### User Story 3 - State file records the tunnel endpoint (Priority: P1)

A developer inspects `.microjail/state.json` after `microjail init --inference llama-cpp`. The state file includes the inference endpoint URL. This URL is used by downstream commands (the inference gate, config generation) to verify and connect to the model. The URL reflects the tunneled endpoint, not a UDS path.

**Why this priority**: The state file is the bridge between `init` and `run`/`lock`. If it records the wrong kind of endpoint (e.g., a UDS path), the gate and config generation will fail.

**Independent Test**: Run `microjail init myproject --inference llama-cpp`; read `.microjail/state.json`; verify `socket_url` is an HTTP URL pointing at the tunneled TCP endpoint (e.g., `http://localhost:8080/v1`), not a UDS path.

**Acceptance Scenarios**:

1. **Given** `--inference llama-cpp`, **When** `microjail init` completes, **Then** `state.json` contains `socket_url` set to an HTTP URL (e.g., `http://localhost:8080/v1`).

2. **Given** no `--inference` flag, **When** `microjail init` completes, **Then** `state.json` contains `socket_url` set to `null`.

---

### User Story 4 - Existing UDS-based configuration is removed (Priority: P2)

The init-command spec previously clarified that "no TCP tunnel" and "no system SDK entry" were the design. This feature reverses that decision. After the pivot, no code path or configuration produces a UDS-based inference passthrough. The inference socket gate no longer checks for a UDS socket file; the workshop.yaml no longer omits the system SDK when inference is enabled.

**Why this priority**: Cleaning up the old path ensures no confusion and no dead code. It is P2 because the new path works independently — the old path simply ceases to be generated.

**Independent Test**: Inspect all generated `workshop.yaml` files and gate logic; verify that no UDS socket path or bind-mount inference mechanism exists anywhere in the codebase.

**Acceptance Scenarios**:

1. **Given** the codebase after this feature, **When** searching for UDS bind-mount or socket-file references in inference paths (`config/`, `gates/`, `commands/`), **Then** no such references remain; all inference reachability is via Workshop tunnel.

2. **Given** the codebase after this feature, **When** `--inference llama-cpp` is used, **Then** the generated `workshop.yaml` always includes a system SDK with a tunnel slot and a project SDK with a corresponding plug.

---

### Edge Cases

- What happens when the host-side inference port is occupied by another service? The gate checks TCP reachability, not service identity. A port accepting connections passes the gate even if it is not llama.cpp. This is the same trust model as UDS: the user is trusted to provide the correct endpoint.
- What happens when Workshop does not support the `tunnel` interface in the user's version? `microjail init` calls `workshop launch` which fails with an error; the user must upgrade Workshop. This is a prerequisite, not a microjail concern.
- What happens when the container is locked? `lock_egress` enumerates ALL NIC-type LXD devices and clears their external routes. The Workshop tunnel is a separate LXD device (not NIC-type) created by Workshop; it is not in the NIC enumeration and survives the lock operation. Inference continues to work during lock.
- What happens with `--force` re-initialisation? The existing environment is refreshed with the new `workshop.yaml` containing the tunnel configuration; the old UDS-based config is replaced.
- What happens when the user changes the port llama-server listens on after init but before run? The state file records the URL from init time. The gate checks the host-side port at that URL, so a mismatch causes a gate failure. The user must re-initialise or update the configuration to match the new port.
- What happens during unlock if the container is running? `unlock_egress` re-adds the container to the `workshopbr0` network. If the container is not running, the network re-attachment is skipped.

### Functional Requirements

- **FR-001**: When `--inference llama-cpp` is specified, `microjail init` MUST include a `system` SDK entry in `workshop.yaml` with a `slots` section that declares a tunnel slot named `llama-cpp` for the inference endpoint. The slot MUST use `interface: tunnel` and an `endpoint` value pointing at the host-side inference address (e.g., `localhost:8080`). The system SDK MUST NOT include a `plugs` section.
- **FR-002**: When `--inference llama-cpp` is specified, `microjail init` MUST include a project SDK entry named `llama-cpp` in `workshop.yaml` with a `plugs` section that declares a tunnel plug named `llama-cpp` corresponding to the system SDK's slot. The plug MUST use `interface: tunnel`. The project SDK MUST NOT include a `slots` section.

- **FR-003**: When `--inference llama-cpp` is NOT specified, `microjail init` MUST NOT include a system SDK entry or any tunnel slot/plug entries in `workshop.yaml`.

- **FR-004**: When `--inference llama-cpp` is specified, `microjail init` MUST write `socket_url` to `.microjail/state.json` as an HTTP URL pointing at the tunneled inference endpoint inside the container (e.g., `http://localhost:8080/v1`). The URL MUST NOT be a UDS path (`http+unix://` or `unix://`).
- **FR-005**: When `--inference llama-cpp` is NOT specified, `microjail init` MUST write `socket_url` as `null` in `.microjail/state.json`.

- **FR-006**: When `--agent opencode` is specified alongside `--inference llama-cpp`, `microjail init` MUST write `opencode.jsonc` with `baseURL` set to the same HTTP URL stored in `socket_url`. The `baseURL` MUST NOT reference a UDS socket path.

- **FR-007**: The inference gate (`check_inference_socket`) MUST verify that the host-side endpoint extracted from `state.socket_url` is accepting TCP connections. It MUST NOT check for the existence of a UDS socket file.

- **FR-008**: The inference gate MUST continue to be skipped when `state.inference` is `None`, exactly as before.

- **FR-009**: The inference gate MUST report a clear failure message including the host and port that could not be reached when the TCP connection fails.

- **FR-010**: All UDS-specific code paths in the inference gate (UDS socket path extraction, socket file existence check, Unix socket connection attempt) MUST be removed. The gate MUST only perform a TCP reachability check.

- **FR-011**: The default inference endpoint for `--inference llama-cpp` remains `http://127.0.0.1:8080/v1`. The port and path are fixed for P1 and may be made configurable in a future feature.

- **FR-012**: `workshop.yaml` generation MUST place the project inference SDK and the system SDK entries after any `opencode` and `skills` SDK entries, so the file remains human-readable.

- **FR-013**: `microjail init --force` MUST refresh the Workshop environment with the new `workshop.yaml` containing the tunnel configuration, replacing any previous configuration (including any prior UDS-based setup).

- **FR-014**: `unlock_egress` MUST restore routes on ALL NIC devices (symmetric to `lock_egress`); it MUST NOT restore routes only on the first NIC.

- **FR-015**: When unlocking, if the Workshop container is running, `unlock_egress` MUST re-add the container to the `workshopbr0` network. If the container is not running, this step MUST be skipped.

### Key Entities

- **System SDK slot**: An entry in `workshop.yaml` under the `system` SDK that uses Workshop's `tunnel` interface to expose a host-side TCP endpoint (e.g., `localhost:8080`) into the container. Declared with `interface: tunnel` and `endpoint: <host-address>`. The system SDK contains only `slots` (no `plugs`); it provides the endpoint.

- **Project SDK plug**: An entry in `workshop.yaml` under a project-level SDK that uses Workshop's `tunnel` interface to consume the system SDK's slot, making the endpoint reachable from inside the container. Declared with `interface: tunnel` and connects by name to the system slot. The project SDK contains only `plugs` (no `slots`); it consumes the endpoint.

- **Tunneled socket URL**: The HTTP URL stored in `state.socket_url` and referenced in `opencode.jsonc`. Represents the endpoint as seen from inside the container after Workshop's tunnel establishes the connection.

- **Inference gate**: The lock gate (formerly `inference-socket`) that verifies the host-side inference endpoint is reachable before the workload starts. Pivoted from UDS file-existence check to TCP connection check.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer running `microjail init --inference llama-cpp --agent opencode` and then `microjail run -- <command>` can verify that the inference endpoint is reachable from inside the container via the Workshop tunnel, without any UDS socket file present in the workspace.

- **SC-002**: The inference gate fails within 5 seconds when the host-side port is not listening, producing a human-readable error naming the unreachable endpoint and port.

- **SC-003**: No UDS socket path or bind-mount inference mechanism exists anywhere in the generated configuration files or the inference gate code after this feature is implemented.

- **SC-004**: Running `microjail init --inference llama-cpp` twice (once without `--force`, failing; once with `--force`, succeeding) produces a valid `workshop.yaml` with tunnel configuration on the second run.

- **SC-005**: When `--inference` is not specified, the generated `workshop.yaml` is identical to what would have been generated before this feature (no system SDK, no tunnel entries), preserving backward compatibility for non-inference use cases.

## Assumptions

- Workshop's `tunnel` interface proxies TCP connections from the host-side endpoint to the container, making the same port available at `localhost:<port>` inside the container. The exact address inside the container matches the `endpoint` field in the system SDK slot.

- The default inference endpoint for `--inference llama-cpp` is `localhost:8080` on the host, producing `http://localhost:8080/v1` as the container-side URL in `opencode.jsonc` and `state.json`.

- Workshop must be installed at a version that supports the `tunnel` interface; `microjail init` does not validate Workshop version — a launch failure is the user's signal to upgrade.

- The project SDK name for inference is derived from the inference provider: when `--inference llama-cpp` is specified, the project SDK is named `llama-cpp`. The slot and plug in the system and project SDKs respectively are also named `llama-cpp` (matching the inference provider). For a hypothetical future `--inference foo-bar`, they would be named `foo-bar`.

- `lock_egress` enumerates ALL LXD devices whose type contains "nic" and clears their external routes. The Workshop tunnel is a separate LXD device (not NIC-type) created by Workshop during launch; it survives the lock operation untouched because it is not in the NIC enumeration. This is a dependency on Workshop's current tunnel implementation; if Workshop changes the tunnel device type to a NIC, `lock_egress` would need corresponding changes.

- The `opencode.jsonc` generation does not change structurally — only the source of the `baseURL` changes (from potential UDS path to guaranteed HTTP URL).

- The inference gate checks host-side reachability only; it does not verify the tunnel is active (that is Workshop's responsibility after launch).

- `unlock_egress` re-adds the container to the `workshopbr0` bridge network during unlock if the container is running. If the container is not running, the re-attachment is skipped.
