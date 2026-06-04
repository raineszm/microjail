# ADR: CTF thin wrapper over microjail config/state

Date: 2026-06-04
Status: Accepted

## Context

The CTF runner had grown a parallel Workshop YAML/state implementation. That duplicated microjail behavior and made containment wiring harder to audit.

## Decision

- Delete the CTF-specific Workshop config generator and use `microjail.config.workshop` instead.
- Extend `AgentHarness` with `"omp"` so CTF can use the same `EnvironmentConfig` model as normal init flows.
- Add `EnvironmentConfig.inference_endpoint` so YAML generation can target arbitrary host inference endpoints without changing state shape.
- Use project-local inference SDK generation via `generate_sdk_yaml()` and shared plug/slot constants.
- Persist CTF state through `EnvironmentState.to_json()` instead of a private JSON template.
- Scope `check_config_readonly` to `agent == "opencode"`; non-opencode agents should not require `opencode.jsonc`.

## Consequences

- There is one Workshop YAML generation path for both `microjail init` and the CTF runner.
- CTF remains a thin orchestration wrapper around shared config/state primitives.
- Future changes to inference plug/slot naming happen in one module.
- `omp` environments can lock without a false config-readonly gate failure.
