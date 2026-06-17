# Microjail UX TODOs

## 1. Endpoint capability setup UX

- Add `microjail cap add endpoint NAME HOST_ENDPOINT [--container-endpoint HOST:PORT] [--fatal] [--replace] [--apply]`.
- Add `microjail cap remove endpoint NAME [--apply]`.
- Validate endpoint names as Workshop identifiers: starts with a letter, then letters/digits/hyphens.
- Validate endpoint values as simple `HOST:PORT`; reject URLs, missing ports, non-numeric ports, and out-of-range ports.
- Make same-value add idempotent; require `--replace` for changed endpoint fields, including `--fatal`.
- Keep plain add/remove config-only: save without warning when not launched; save with warnings when off/stopped or ready+unlocked; fail before saving when pending, ready+locked, or Workshop state cannot be determined.
- Define `--apply` state rules: fail before saving for not-launched, pending, ready+locked, or unknown state; update Microjail and Workshop declarations without refresh/connect for off/stopped; perform live revoke/provide/apply for ready+unlocked.
- Fix user-facing docs/examples so endpoint capability config matches the actual schema (`host_endpoint`, not stale `endpoint`).
- Future direction: make endpoint parsing more robust, including broader valid endpoint forms beyond simple `HOST:PORT`.
- Future direction: consider comment/format preservation for CLI-edited config if users start treating `.microjail/config.yaml` as hand-authored policy.

## 2. Batched refreshes

Treat refresh batching as a separate performance/change-safety pass.

- Avoid `workshop refresh` once per endpoint capability during apply/release.
- Stage endpoint plug/slot YAML mutations, write once, refresh once if anything changed, then connect/disconnect as needed.
- Preserve stateless safety: do not introduce broad cached lock state.
- Add tests proving multiple endpoint capabilities trigger one refresh, not N refreshes.

## 3. Status/diagnostics UX

Add visibility after the setup flow is better.

- Add `microjail status` to show initialization, workshop state, declared capabilities, gates, and live policy state.
- Add `microjail validate` to run the same Lockdown/config validation used before `lock`, including duplicate Capability names and endpoint syntax, without applying policy.
- Keep output actionable: show what is wrong and the next command to run.
- Future direction: consider explicit active-workload detection/recording so management commands can distinguish “Gates happen to hold” from “a supervised workload is running”.
