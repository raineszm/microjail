# Quickstart: microjail init

**Feature**: `specs/20260529-154152-init-command/`
**Date**: 2026-05-29

This guide walks through using `microjail init` once it is implemented. It is also the
acceptance validation script for the implementation: follow these steps on a machine with
Workshop and LXD installed and verify each expected outcome.

---

## Prerequisites

Before running `microjail init`, ensure:

1. **Workshop is installed** — `workshop --version` exits 0.
2. **LXD is running** — `lxc version` exits 0.
3. **microjail is installed** — `microjail --help` exits 0.
4. **For inference**: llama.cpp is running on the host and listening on `localhost:8080`.
   A socat bridge may be required if llama.cpp exposes a UDS socket rather than TCP directly
   (see research.md §3 for details).

---

## Scenario A: Full init (agent + local inference)

```bash
mkdir ~/myproject && cd ~/myproject

microjail init myproject --inference llama-cpp --agent opencode
```

**Expected output**:
```
Environment 'myproject' created.

  workshop.yaml   → /home/<user>/myproject/workshop.yaml
  opencode.jsonc  → /home/<user>/myproject/opencode.jsonc
  state           → /home/<user>/myproject/.microjail/state.json
```

**Verify files were written**:
```bash
ls workshop.yaml opencode.jsonc .microjail/state.json
```

**Verify workshop.yaml content** — must contain `se-llama` tunnel:
```bash
grep se-llama workshop.yaml
```

**Verify opencode.jsonc disables remote providers** — must show `false` for all known
providers:
```bash
python3 -c "
import json
with open('opencode.jsonc') as f:
    cfg = json.load(f)
remote = {k: v for k, v in cfg['provider'].items() if k != 'llama.cpp'}
assert all(v.get('enabled') is False for v in remote.values()), \
    f'Remote providers not disabled: {remote}'
print('All remote providers disabled. OK.')
"
```

**Verify state.json**:
```bash
python3 -c "
import json
with open('.microjail/state.json') as f:
    s = json.load(f)
assert s['name'] == 'myproject'
assert s['inference'] == 'llama-cpp'
assert s['agent'] == 'opencode'
print('State OK:', s)
"
```

**Verify Workshop environment exists**:
```bash
workshop list | grep myproject
```

---

## Scenario B: Bare init (no flags)

```bash
mkdir ~/barejail && cd ~/barejail

microjail init barejail
```

**Expected output**: success message without `opencode.jsonc` line.

**Verify no opencode.jsonc was written**:
```bash
test ! -f opencode.jsonc && echo "opencode.jsonc absent — correct"
```

**Verify workshop.yaml has no tunnel**:
```bash
python3 -c "
import yaml
with open('workshop.yaml') as f:
    cfg = yaml.safe_load(f)
sdk_names = [s['name'] for s in (cfg.get('sdks') or [])]
assert 'system' not in sdk_names, 'system SDK should not be present without --inference'
print('No tunnel SDK present. OK.')
"
```

---

## Scenario C: Duplicate name is rejected

```bash
cd ~/myproject  # environment already created above
microjail init myproject
```

**Expected**: exits non-zero with message:
```
Error: Environment 'myproject' already exists. Use --force to reinitialise.
```

---

## Scenario D: Missing prerequisites

On a machine without Workshop:
```bash
microjail init testenv
```

**Expected**: exits non-zero with message naming `workshop` as the missing tool.

---

## Teardown

```bash
workshop delete myproject
rm -rf ~/myproject ~/barejail
```
