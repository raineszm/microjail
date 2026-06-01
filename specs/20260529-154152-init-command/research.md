# Research: microjail init Command

**Feature**: `specs/20260529-154152-init-command/`
**Date**: 2026-05-29

## 1. Workshop CLI Interface

### Decision
Invoke Workshop via `subprocess` using the `workshop` CLI binary. Do not attempt to use a
Workshop Python SDK (none is published). Verify post-creation state via
`workshop info <name> --project <workspace>` to ensure the environment exists in Workshop’s
LXD project.
### Rationale
Workshop is a Canonical CLI tool. Its public interface is the `workshop` binary. Using
subprocess keeps the coupling loose: microjail delegates environment lifecycle to Workshop
and doesn't replicate its logic. Since we already shell out to `workshop`, shelling out to
`lxc` for verification is consistent and removes `pylxd` as a runtime dependency.

### Workshop CLI commands used

| Operation | Command |
|-----------|---------|
| Create environment | `workshop launch <name> --project <project_dir>` |
| Check environment exists | `workshop info <name> --project <project_dir>` |
| Remove environment | `workshop remove <name> --project <project_dir>` |

Workshop stores environment definitions at `<project_dir>/.workshop/<name>.yaml`.

### Post-creation verification
After `workshop create`, verify the environment exists using the LXD client binary:

```python
import subprocess

result = subprocess.run(
    ["lxc", "info", env_name],
    capture_output=True,
)
if result.returncode != 0:
    raise RuntimeError(
        f"Environment '{env_name}' was not found after creation. "
        f"lxc output: {result.stderr.decode()}"
    )
```

This satisfies FR-007: the check is independent of the `workshop create` return code.

### Alternatives considered
- **pylxd for verification**: Rejected. Since we already shell out to `workshop`, adding a
  Python LXD API client just for verification introduces unnecessary coupling and a heavier
  dependency. `lxc info` is a direct, auditable check.
- **Workshop Python SDK**: Does not exist as a published package at time of writing.

---

## 2. Prerequisite Detection

### Decision
Check for `workshop` and `lxd` availability at command start, before any file I/O.

### Implementation
```python
import shutil, subprocess

def check_prerequisites() -> None:
    if shutil.which("workshop") is None:
        raise RuntimeError("workshop not found on PATH. Install Workshop: ...")
    result = subprocess.run(["lxc", "version"], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError("LXD not available. Check that LXD is installed and running.")
```

`shutil.which` checks PATH. LXD availability is probed via `lxc version` (the LXD client
binary). Using `lxc` rather than trying to connect via `pylxd` first gives a clear binary
pass/fail without an exception stack trace on a clean machine.

### Alternatives considered
- **Defer to Workshop**: Let `workshop create` fail and surface its error. Rejected: Workshop
  error messages are not always actionable; microjail MUST name the missing prerequisite
  explicitly (FR-009).

---

## 3. UDS Transport for Local Inference

### Decision
Use UDS via bind-mount. `workshop.yaml` does NOT include a `system` SDK or any TCP tunnel
configuration. `opencode.jsonc` points at the UDS socket file in the workspace directory.
A socat bridge may be required at runtime if OpenCode cannot connect to a raw UDS path directly.

### Rationale
The TCP tunnel approach (from `tmp/workshop.yaml`) has been explicitly rejected. The bind-mount
path is:
1. llama.cpp exposes a UDS socket file in the workspace directory (e.g., `llama.sock`).
2. Workshop bind-mounts the workspace into the container by default.
3. OpenCode inside the container connects to the socket via the mounted path.

No Workshop tunnel configuration is required. `workshop.yaml` is simpler as a result.

### Known risk: OpenCode UDS support
OpenCode uses the `@ai-sdk/openai-compatible` or similar provider packages built on Node.js
`fetch`, which may not support `unix://` scheme URLs natively. If this is confirmed during
implementation, a socat bridge on the host:

```bash
socat TCP-LISTEN:8080,reuseaddr,fork UNIX-CONNECT:/path/to/workspace/llama.sock
```

allows OpenCode to connect via `http://127.0.0.1:8080/v1`. In that case:
- `opencode.jsonc` `baseURL` becomes `http://127.0.0.1:8080/v1`.
- `workshop.yaml` still does NOT include a tunnel — the container connects to the host-side
  socat listener via the loopback interface, not via a Workshop tunnel.

Implementation MUST verify and document which endpoint format is used.

### Implications for FR-004 / FR-005
FR-004: `workshop.yaml` for `--inference llama-cpp` contains `opencode` and `skills` SDKs
only. No `system` SDK. No tunnel entries.
FR-005: `opencode.jsonc` `baseURL` is the UDS socket path (or `http://127.0.0.1:8080/v1`
if socat is needed — to be determined during implementation).

### Alternatives considered
- **TCP tunnel (tmp/ example approach)**: Rejected by user. Removed from P1 scope.
- **socat managed by microjail init**: Out of scope; socat is a host-side responsibility.

---

## 4. opencode.jsonc: Disabling Remote Providers

### Decision
Write `opencode.jsonc` with the `$schema` pointing at the OpenCode config schema and add
explicit `enabled: false` entries for all known built-in OpenCode providers. Only the
`llama.cpp` provider entry is active.

### OpenCode provider config schema
Based on the OpenCode config schema at `https://opencode.ai/config.json`, providers can be
listed under the `provider` key. Providers not listed are not loaded. However, OpenCode also
auto-detects API keys from environment variables (e.g., `ANTHROPIC_API_KEY`) and may enable
built-in providers automatically. To be safe, known providers are explicitly disabled.

Known built-in provider IDs at time of writing: `anthropic`, `openai`, `google`,
`amazon-bedrock`, `azure`, `groq`, `mistral`, `xai`, `deepseek`, `cerebras`.

### Generated opencode.jsonc structure
```jsonc
{
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "anthropic":      { "enabled": false },
        "openai":         { "enabled": false },
        "google":         { "enabled": false },
        "amazon-bedrock": { "enabled": false },
        "azure":          { "enabled": false },
        "groq":           { "enabled": false },
        "mistral":        { "enabled": false },
        "xai":            { "enabled": false },
        "deepseek":       { "enabled": false },
        "cerebras":       { "enabled": false },
        "llama.cpp": {
            "name": "llama-server (local)",
            "options": {
                "baseURL": "<uds-path-or-http-loopback>"
            },
            "models": {}
        }
    },
    "plugin": [
        "context-mode",
        "cc-safety-net"
    ]
}
```

The `npm` field is omitted. OpenCode's built-in provider mechanism is used. The exact
`baseURL` value (UDS path or HTTP loopback) is to be confirmed during implementation.

### Rationale
Writing the full list of disabled providers is explicit and auditable. An auditor can confirm
at a glance that no remote provider is active. This satisfies SC-005 and the constitution's
Principle III (auditability).

### Alternatives considered
- **Omit disabled providers**: Relies on OpenCode not auto-enabling providers from environment
  variables. Rejected: violates Principle II (correctness over confidence).
- **Allowlist-only model**: Only write the active provider, rely on OpenCode's default
  behaviour. Same rejection reason.

---

## 5. State File Format

### Decision
Write `.microjail/state.json` in the workspace root. Schema is a flat JSON object.

```json
{
    "name": "myproject",
    "base_image": "ubuntu@26.04",
    "inference": "llama-cpp",
    "agent": "opencode",
    "socket_path": "<uds-path-or-http-loopback>",
    "created_at": "2026-05-29T15:41:52Z"
}
```

`inference` and `agent` are `null` when the corresponding flags are not passed.
`socket_path` is `null` when no inference backend is configured. The exact value (UDS path
or HTTP loopback) is confirmed during implementation alongside the `baseURL` decision.

### Rationale
Flat JSON is the simplest structure that satisfies FR-010. Downstream commands (`run`,
`unlock`) read the state to know which environment to act on and what gates to apply.

---

## 6. JSONC Serialisation

### Decision
Python's `json` stdlib does not produce JSONC (JSON with Comments). For `opencode.jsonc`,
write standard JSON (valid JSONC) with no comments. The `.jsonc` extension is used because
OpenCode expects it; the content is valid JSON.

### Rationale
Adding a comment-capable serialiser is unnecessary complexity. The generated file is
machine-written and does not require inline comments. Human-readable documentation lives in
this research file and the spec.

### Alternatives considered
- **Add a JSONC library**: Rejected per Principle IV (stdlib first) and YAGNI.

---

## 7. ruamel.yaml for workshop.yaml

### Decision
Use `ruamel.yaml` (not PyYAML) for `workshop.yaml` serialisation. Add `ruamel.yaml` to
project dependencies.

### Rationale
`ruamel.yaml` is preferred over PyYAML for new projects because:
- It preserves key ordering without special configuration (PyYAML requires `sort_keys=False`
  and still has edge cases).
- It produces cleaner YAML output by default (no trailing `\n` issues, better block style).
- It supports YAML 1.2, whereas PyYAML only supports YAML 1.1.
- It is actively maintained.

Usage:
```python
from ruamel.yaml import YAML

yaml = YAML()
yaml.default_flow_style = False
with open("workshop.yaml", "w") as f:
    yaml.dump(data, f)
```

### Alternatives considered
- **PyYAML**: Rejected by user preference. Also YAML 1.1 only and less actively maintained.
- **stdlib (no YAML library)**: Writing YAML by hand with string templates is error-prone
  and not auditable. Rejected.
