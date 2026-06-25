## Context

Endpoint capabilities are currently configured by editing `.microjail/config.yaml` directly. The persisted Lockdown is a declaration, while runtime provisioning is performed later by Lockdown application: Endpoint capabilities write Workshop plug/slot declarations, refresh Workshop, connect the tunnel, and verify reachability.

The design follows ADR 0006: the CLI edits Capability declarations by default, and `--apply` explicitly requests state-sensitive reconciliation/application.

## Goals / Non-Goals

**Goals:**

- Provide a CLI-first workflow for adding, replacing, and removing Endpoint Capability declarations.
- Keep `.microjail/config.yaml` as the reviewable source of truth.
- Validate Capability names and Endpoint syntax before runtime changes.
- Reconcile Microjail-owned Workshop endpoint declarations against current Lockdown declarations during `lock`, `run`, and `shell`.
- Keep config-only edits safe through state preflight, warnings, and later reconciliation.

**Non-Goals:**

- Do not add Gate management commands.
- Do not make `microjail init NAME` optional.
- Do not batch Workshop refreshes; that is a separate performance change.
- Do not preserve YAML comments/formatting beyond the current canonical rewrite behavior.
- Do not add active workload tracking; locked state is conservatively inferred from live Gate checks.
- Do not support URL syntax, IPv6 bracket syntax, or endpoint forms beyond simple `HOST:PORT`.

## Decisions

### Decision 1: Use `cap add/remove endpoint` grammar

Implement a new `cap` command group:

```bash
microjail cap add endpoint NAME HOST_ENDPOINT
microjail cap remove endpoint NAME
```

Endpoint add accepts `--container-endpoint`, `--fatal`, `--replace`, and `--apply`. Endpoint remove accepts `--apply`.

Rationale: `cap` is short enough to avoid repeated `capability` typos, while still naming the domain concept. `add/remove` are declaration-editing verbs, avoiding runtime lifecycle terms such as `provide` and `revoke`. Verb-before-type matches common CLI grammar and leaves room for future capability types.

### Decision 2: Validate Lockdown declarations explicitly after loading

Add explicit validation after deserialization and before commands mutate or apply policy. Validation reports all errors and covers:

- Capability names are globally unique within a Lockdown.
- Endpoint names match Workshop identifier syntax: starts with a letter, then letters, digits, or hyphens.
- Endpoint values are simple `HOST:PORT` strings: host is non-empty, contains no whitespace, `/`, or `:`, and port is an integer in `1..65535`.

`lock`, `run`, `shell`, `cap`, and future `validate` should use full validation. `unlock` and `destroy` should avoid full semantic validation so cleanup is not blocked by a config mistake.

### Decision 3: Preflight Workshop state before cap edits

Before any `cap` edit, determine Workshop state. If state lookup errors, fail before saving. If the current Lockdown appears applied, detected by any current Gate check returning true, fail before saving.

State behavior:

| Workshop state | Declaration-only edit | Edit with `--apply` |
|---|---|---|
| Not launched | Save declaration change only | Fail before saving |
| Pending | Fail before saving | Fail before saving |
| Off or stopped | Save declaration change and warn | Update Microjail and Workshop declarations; do not start, refresh, or connect |
| Ready and unlocked | Save declaration change and warn | Use the normal Lockdown application path after any required revoke-before-save step |
| Ready and locked | Fail before saving | Fail before saving |
| Unknown/error | Fail before saving | Fail before saving |

Same-value add is idempotent, but still respects state preflight. With `--apply`, same-value add still applies/reconciles the resulting Lockdown.

### Decision 4: Keep config-only edits declaration-only, then reconcile at Lockdown application

Plain `cap add/remove` writes `.microjail/config.yaml` and does not mutate Workshop declarations. It warns when live Workshop declarations may lag the config. This keeps first-run config editing fast and predictable.

To make manual config edits and config-only CLI edits safe, `MicroJail.ensure()` must reconcile Microjail-owned Workshop endpoint declarations against the current Endpoint Capability declarations before providing declared endpoints.

### Decision 5: Reconcile stale endpoint declarations before providing declared endpoints

At the start of Capability application:

1. Compute declared Endpoint capability names from the current Lockdown.
2. Read Microjail-owned plugs from `.workshop/microjail/sdk.yaml`.
3. For each Microjail-owned plug not represented by the current Lockdown, disconnect/remove that plug and the same-named system slot.
4. If stale cleanup fails, report Capability application failure and stop before Gate enforcement.
5. Provide declared Endpoint capabilities normally.

Cleanup is driven by Microjail-owned plugs, not by scanning and deleting arbitrary Workshop system slots. Stale cleanup is not rolled back; it removes unauthorized access and moves the environment toward the current Lockdown source of truth.

### Decision 6: Preserve revoke-before-save safety for apply remove/replace

For ready+unlocked `cap remove endpoint --apply` and changed `cap add endpoint --replace --apply`, revoke the old endpoint before saving the new config. If revoke fails, the config remains aligned with the old live state. After saving, run the normal Lockdown application path to verify/provide the resulting policy.

For off/stopped `--apply`, update Microjail and Workshop declaration files only. Do not start, refresh, connect, or disconnect runtime state.

## Risks / Trade-offs

- **Risk: `cap` edits depend on live state checks.** This can make declaration edits fail when Workshop state cannot be determined. This is intentional: safety beats silently changing policy under an unknown live environment.
- **Risk: stale cleanup changes current `lock` behavior.** Ordinary declared Capability failures during `lock` can still continue to Gates, but stale cleanup failures stop before Gates. This asymmetry is deliberate because extra undeclared access is more dangerous than missing declared access.
- **Risk: canonical YAML rewrite drops comments/formatting.** This follows existing `MicroJail.save()` behavior. Comment preservation remains a future direction.
- **Risk: endpoint validation is intentionally narrow.** The first change rejects URLs, IPv6 bracket syntax, and broader endpoint forms. Runtime reachability remains separate from syntax validation.
