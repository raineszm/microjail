# Feature Specification: microjail init Command

**Feature Branch**: `20260529-154152-init-command`

**Created**: 2026-05-29

**Status**: Draft

**Input**: User description: "Implement the init command. Amongst other things it should create an
opinionated opencode.json in the project folder and a workshop.yaml. Examples from a project I set
up manually are in the tmp/ folder of this directory."

## Clarifications

### Session 2026-05-29

- Q: Should `opencode.jsonc` disable all providers other than the local inference provider?
  → A: Yes. All providers other than the local llama-cpp provider MUST be disabled.
- Q: For P1, which transport should `microjail init` configure for local inference communication?
  → A: UDS via bind-mount (llama.cpp drops a socket file in the workspace; opencode points at
  that socket path). Caveat: OpenCode may require an HTTP endpoint, so a socat/systemd bridge
  from the UDS to an HTTP listener may be needed. This is a known technical risk, not a blocker
  for P1; the spec records it and implementation MUST document whether the bridge is required.

### Session 2026-05-29 (amendment)

- Q: Which YAML library should be used for `workshop.yaml` generation?
  → A: `ruamel.yaml` (not PyYAML).
- Q: Should `workshop.yaml` include a TCP tunnel (system SDK plug/slot) for the inference backend?
  → A: No. The TCP tunnel is removed entirely. The `system` SDK entry is omitted. UDS via
  bind-mount is the mechanism; no Workshop tunnel configuration is needed.
- Q: Should `opencode.jsonc` include the `npm` field to install the `@ai-sdk/openai-compatible`
  package?
  → A: No. Do not include any `npm` field or ai-sdk dependency. Use OpenCode's built-in provider
  configuration only.
- Q: Should Workshop environment post-creation verification use `pylxd` or `lxc` subprocess?
  → A: Use `lxc` subprocess calls (consistent with the `workshop` subprocess approach). `pylxd`
  is not used for verification.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a jailed environment for an AI coding agent (Priority: P1)

A developer wants to run an AI coding agent against a local workspace without allowing the agent
any network access. They run `microjail init` with a project name and intent flags, and receive a
ready-to-use environment with all config files written to the workspace.

**Why this priority**: This is the primary use case described in the README and the prerequisite
for every other microjail operation. Nothing can be locked, run, or unlocked without an
initialised environment.

**Independent Test**: Run `microjail init myproject --inference llama-cpp --agent opencode` in
a directory with Workshop and LXD available; verify the Workshop environment exists,
`workshop.yaml` is present in the workspace, and `opencode.jsonc` is written to the workspace
root configured to point at the llama-cpp UDS path, with all other providers disabled.

**Acceptance Scenarios**:

1. **Given** a host with Workshop and LXD installed, **When** the user runs
   `microjail init myproject --inference llama-cpp --agent opencode`,
   **Then** a Workshop environment named `myproject` is created, `workshop.yaml` is written to
   the workspace, `opencode.jsonc` is written to the workspace root with the local llama-cpp
   provider configured and all other providers disabled, and the command exits zero.

2. **Given** the user runs `microjail init` without a project name,
   **Then** the command exits non-zero and prints a clear error message naming the missing
   argument.

3. **Given** an environment named `myproject` already exists,
   **When** the user runs `microjail init myproject` again,
   **Then** the command exits non-zero with a message indicating the environment already exists,
   and no files are modified.

---

### User Story 2 - Create an environment without agent or inference (Priority: P2)

A developer wants a basic network-sealed environment for running arbitrary untrusted scripts,
without any AI agent or local model. They run `microjail init` with no intent flags and receive
a minimal environment.

**Why this priority**: The README explicitly states the tool is not agent-only. Supporting bare
init without intent flags ensures the core lifecycle is useful for any untrusted workload.

**Independent Test**: Run `microjail init myproject` (no flags); verify the Workshop environment
exists and `workshop.yaml` is written. Verify `opencode.jsonc` is NOT written (no agent requested).

**Acceptance Scenarios**:

1. **Given** a host with Workshop and LXD available, **When** the user runs
   `microjail init myproject` with no intent flags,
   **Then** a Workshop environment is created, `workshop.yaml` is written, and no agent config
   file is written.

2. **Given** the user passes an unrecognised intent flag value,
   **Then** the command exits non-zero and lists the supported values.

---

### Edge Cases

- What happens when Workshop is not installed or LXD is not running? The command MUST exit
  non-zero with a message that names the missing prerequisite and explains how to resolve it.
- What happens when the workspace directory does not exist or is not writable? The command MUST
  fail before creating the Workshop environment, to avoid partial state.
- What happens when `workshop.yaml` already exists in the workspace? The command MUST refuse to
  overwrite it unless an explicit `--force` flag is provided, to prevent silent data loss.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The command MUST accept a positional `<name>` argument identifying the environment.
- **FR-002**: The command MUST accept an `--inference` option; the only supported value for P1 is
  `llama-cpp`. Passing an unsupported value MUST produce a non-zero exit and a clear message.
- **FR-003**: The command MUST accept an `--agent` option; the only supported value for P1 is
  `opencode`. Passing an unsupported value MUST produce a non-zero exit and a clear message.
- **FR-004**: The command MUST always write `.workshop/<NAME>.yaml` in the workspace declaring the
  environment name and base image. The `sdks` list is populated based on intent flags: when
  `--inference llama-cpp` and/or `--agent opencode` are specified, the relevant SDKs are
  included; when no intent flags are given, `sdks` is an empty list. No TCP tunnel or `system`
  SDK entry is ever included; inference reaches the container via the UDS socket file in the
  bind-mounted workspace directory.
- **FR-005**: When `--agent opencode` is specified, the command MUST write `opencode.jsonc` to
  the workspace root with:
  - The local llama-cpp provider configured using OpenCode's built-in provider mechanism (no
    `npm` field; no ai-sdk package installation required).
  - All built-in and default remote providers explicitly disabled, so the agent cannot fall back
    to a remote API.
  - The `context-mode` and `cc-safety-net` plugins enabled.
- **FR-006**: The command MUST create a Workshop environment using the declared name and base
  image (`ubuntu@26.04` for P1).
- **FR-007**: The command MUST verify the Workshop environment was successfully created by running
  `workshop info <name> --project <workspace>` as a subprocess and confirming exit code 0. It MUST NOT assume success from
  the absence of an error on the `workshop launch` call alone.
- **FR-008**: If an environment with the given name already exists, the command MUST refuse and
  exit non-zero without modifying any files.
- **FR-009**: If Workshop or LXD prerequisites are absent, the command MUST exit non-zero and
  name the missing prerequisite in the error message.
- **FR-010**: The command MUST persist environment state (name, intent flags, socket paths) to
  `.microjail/state.json` in the workspace directory so downstream commands (`run`, `unlock`)
  can locate and act on the environment without the user re-specifying flags.
- **FR-011**: All file writes (`workshop.yaml`, `opencode.jsonc`, state file) MUST be completed
  successfully before the Workshop environment creation call is made, so a creation failure
  leaves no partial state inside the remote environment.

### Known Technical Risk

The P1 inference path uses a UDS socket file bind-mounted into the container via Workshop's
workspace mount. OpenCode's provider configuration accepts a socket path for the local provider.
However, if OpenCode requires an HTTP endpoint rather than a raw UDS path, a bridge process
(socat or a systemd socket unit on the host) will be needed to proxy the UDS to a local HTTP
listener. Implementation MUST verify this during development and document whether the bridge is
required. If the bridge is required, FR-005 is updated to reflect the HTTP endpoint rather than
the socket path; the spec does not need a formal amendment for this, as it is a transport detail.

### Key Entities

- **Environment**: A named Workshop/LXD container. Key attributes: name, base image, provisioned
  SDKs. One environment per `microjail init` invocation.
- **Intent flags**: Declarative options (`--inference`, `--agent`) that determine which config
  files are generated and which Workshop SDKs are declared.
- **workshop.yaml**: The Workshop environment descriptor written to the workspace root. Declares
  the environment name, base image, and required SDKs. Contains no TCP tunnel configuration;
  inference is delivered via the UDS socket file in the bind-mounted workspace.
- **opencode.jsonc**: The OpenCode agent configuration written to the workspace root. Declares
  the local inference provider using OpenCode's built-in mechanism (no npm dependency), disables
  all other providers, and enables the required plugins.
- **State file** (`.microjail/state.json`): Written to the workspace directory. Captures
  environment name, intent flags, and the resolved inference socket path for downstream commands.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with Workshop and LXD installed can run `microjail init` and have a working
  environment ready (all config files written, Workshop environment created) in under 60 seconds
  on a local machine.
- **SC-002**: Running `microjail init` with invalid or missing arguments always produces a
  human-readable error message and exits non-zero; zero ambiguous failures.
- **SC-003**: Running `microjail init` twice with the same name never silently overwrites
  existing config files or creates a duplicate environment.
- **SC-004**: A developer unfamiliar with Workshop can follow the output of `microjail init
  --help` alone to understand all required and optional arguments.
- **SC-005**: When `--agent opencode` is specified, the written `opencode.jsonc` contains no
  enabled remote provider entries; the only active provider is the local llama-cpp endpoint.

## Assumptions

- Workshop and LXD must be installed and operational on the host before `microjail init` is run;
  microjail does not install them. Workshop environment existence is verified via `lxc info`.
- The base image for P1 is fixed at `ubuntu@26.04`; making it configurable is explicitly deferred
  to a future feature.
- The llama-cpp UDS socket file is placed in the workspace directory by the user before running
  the workload; microjail writes the socket path into `opencode.jsonc` but does not start
  llama.cpp. A socat bridge may be needed if OpenCode requires HTTP rather than a raw UDS path.
- The workspace directory is the current working directory; this feature does not introduce a
  `--workspace` flag.
- `opencode.jsonc` written by microjail is opinionated and not intended to be user-edited;
  users who need a different config should manage it manually after init.
- The state file is written to `.microjail/state.json` in the workspace directory.
- Multiple environments per workspace directory are out of scope; one workspace, one environment.
