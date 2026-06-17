# 0005 Endpoint capability CLI separates declarations from runtime application

Users need a safe CLI path for common Endpoint capability setup without editing YAML by hand, but Capability declarations are not the same as runtime provisioning. We chose `microjail cap add endpoint ...` and `microjail cap remove endpoint ...` as declaration-editing commands, with `--apply` as an explicit request to reconcile the Workshop declarations and apply the resulting Lockdown when the Workshop state makes that safe.

## Considered Options

- **Use intent verbs such as `allow` and `deny`** — Friendly for Endpoint capabilities, but awkward for future Gate management and easy to confuse with runtime authorization state.
- **Use runtime lifecycle verbs such as `provide`, `revoke`, `enforce`, and `release`** — Mirrors implementation terms, but incorrectly suggests the command always changes live runtime state.
- **Use `cap add/remove` for Capability declarations and reserve Gate-specific verbs for future Gate declaration editing** — Slightly more domain-oriented, but keeps declaration edits separate from runtime lifecycle operations.

## Decision

We chose `microjail cap add endpoint NAME HOST_ENDPOINT` and `microjail cap remove endpoint NAME` for Endpoint Capability declaration edits. The default behavior edits the reviewable `.microjail/config.yaml` Lockdown declaration only. `--apply` is required when the user wants Microjail to update Workshop declarations and, when the Workshop is ready and unlocked, run the normal Lockdown application path.

`cap` commands must refuse edits when the current Lockdown appears applied, detected by any current Gate check returning true, because changing declarations under an active workload or locked environment makes the policy boundary unclear. If the Workshop is not launched, `--apply` fails before saving; users can omit `--apply` for declaration-only setup. If the Workshop is off or stopped, `--apply` updates Microjail and Workshop declaration files without starting, refreshing, or connecting the Workshop.

| Workshop state | Declaration-only `cap` edit | `cap` edit with `--apply` |
|---|---|---|
| Not launched | Save declaration change only | Fail before saving |
| Pending | Fail before saving | Fail before saving |
| Off or stopped | Save declaration change only | Update Microjail and Workshop declaration files; do not start, refresh, or connect |
| Ready and unlocked | Save declaration change and warn that live state was not changed | Reconcile/provide through the normal Lockdown application path |
| Ready and locked | Fail before saving | Fail before saving |
| Unknown or lookup error | Fail before saving | Fail before saving |

## Consequences

- The CLI grammar stays stable for future Gate commands instead of overloading `allow`/`deny` across Capabilities and Gates.
- Lockdown application must reconcile Microjail-owned Workshop endpoint declarations with current Endpoint Capability declarations before providing declared Endpoint capabilities so manual config edits and config-only CLI edits converge on the declared policy at the next `lock`, `run`, or `shell`.
- `--apply` is intentionally state-sensitive: it is a safe reconciliation shortcut, not an implicit Workshop launch or a promise to mutate a locked environment.
- Stale endpoint cleanup is not rolled back. Removing undeclared Microjail-owned access moves the environment toward the current Lockdown source of truth; restoring stale access after a later failure would reintroduce extra access.
- Stale cleanup failures are stricter than ordinary Capability provision failures: they stop before Gate enforcement, including during `lock`, because extra undeclared access is more dangerous than missing declared access.
