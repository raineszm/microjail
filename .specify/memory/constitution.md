<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.0.1

Modified principles:
  - IV. Idiomatic Python — added explicit prohibition on `# noqa` suppressions

Sections added:
  - None

Sections removed:
  - None

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — Constitution Check section is generic; aligns with updated principles.
  - ✅ .specify/templates/spec-template.md — MUST/SHOULD language matches constitution style; no changes required.
  - ✅ .specify/templates/tasks-template.md — Task structure supports safety-first phases; no changes required.

Deferred TODOs:
  - TODO(RATIFICATION_DATE): original adoption date unknown; marked below.
-->

# microjail Constitution

## Core Principles

### I. Safety First

The lock-then-run lifecycle is the product's primary guarantee. Every operation in the `run`
path MUST verify its preconditions before proceeding — not assume them. Gates are not optional
checks; they are blockers. If any gate fails, the workload MUST NOT start.

- Egress MUST be confirmed down, not merely requested down, before the workload spawns.
- Inference socket presence and reachability MUST be verified when local inference is enabled.
- Workspace mount state MUST be asserted before the workload sees the filesystem.
- New gates MUST default to blocking (not advisory) unless explicitly designed otherwise and
  justified in code and documentation.

*Rationale*: The entire value proposition of microjail rests on the correctness of the lock.
A workload that starts with an unverified assumption about network isolation is not jailed.

### II. Correctness Over Confidence

Confidence is not evidence. Code MUST NOT skip verification steps because the outcome "should"
be fine. Every assertion about system state MUST be grounded in an observable fact — a return
code, a probe result, a filesystem stat — not an inference.

- Double-check: if a step says it succeeded, verify the postcondition independently where
  feasible.
- Be skeptical of OS and library calls that return success codes without guaranteeing the
  intended effect (e.g., `ip link set down` does not mean packets have stopped flowing).
- Document explicitly what is and is not verified, so reviewers can audit the gap.
- Uncertainty MUST surface as an error or a logged warning — never swallowed.

*Rationale*: Security-sensitive systems fail at the seams between "requested" and "actual".
Demanding evidence at each step keeps the seams visible.

### III. Human Readability & Auditability

Code is written once and read many times, often under pressure. The primary audience is a
human auditor trying to answer: "does this actually do what it claims?"

- Prefer explicit, linear control flow over clever abstractions.
- Names MUST describe intent, not implementation detail (e.g., `verify_egress_down` not
  `check_net`).
- Non-obvious decisions MUST carry an inline comment explaining *why*, not *what*.
- Log entries MUST be human-parseable at the point of writing, not only after post-processing.
- Public interfaces MUST have docstrings. Internal helpers MAY omit them when the name and
  types are self-explanatory.

*Rationale*: An auditor who cannot follow the code cannot confirm the safety guarantee.
Readability is a security property here.

### IV. Idiomatic Python

Use the language the way the language is meant to be used. Non-idiomatic patterns increase
cognitive load for reviewers familiar with the ecosystem.

- Follow PEP 8 and project linting/formatting rules (ruff); no exceptions without comment.
- Linter warnings MUST be fixed at the source. Suppression via `# noqa` comments is
  forbidden. If a linter rule is wrong for the project, disable it in the ruff configuration
  file so the decision is explicit, reviewed, and applies consistently — not silently
  overridden line by line.
- Use standard library primitives before reaching for third-party dependencies.
- Prefer `dataclasses`, `NamedTuple`, or `TypedDict` for structured data over ad-hoc dicts.
- Use type annotations throughout. Untyped public functions are not acceptable.
- Exceptions for control flow MUST use the appropriate exception type and carry a message.

*Rationale*: Idiomatic code is predictable. Predictable code is auditable.

### V. Fail Loudly, Fail Clearly

Silent failures are forbidden. When something goes wrong, the system MUST say so in terms a
human can act on.

- All error paths MUST produce a message that identifies: what failed, why it failed (as
  specifically as known), and what the caller should do next.
- Errors MUST propagate to the CLI as a non-zero exit code.
- Catching an exception only to swallow it is a defect. If an exception is caught to log
  and re-raise, it MUST still re-raise (or exit non-zero at the boundary).
- Warnings that signal a degraded safety guarantee MUST be printed to stderr and logged,
  never omitted for UX cleanliness.

*Rationale*: A jail that silently fails open is worse than no jail at all.

## Security & Isolation Constraints

These constraints apply to the lock/unlock lifecycle and cannot be overridden by feature work
without a governance amendment:

- **No implicit trust of tool output**: Shell command success codes are necessary but not
  sufficient. Probe the intended effect where possible (e.g., attempt an outbound connection
  after locking and expect failure).
- **Principle of least exposure**: Provisioning wrappers (`apt`, `uv`) MUST NOT be available
  inside a locked environment. Locking implies provisioning is complete.
- **Audit trail**: Every `run` invocation MUST log the gate results, the workload command,
  start time, and exit code. This log MUST be retained after unlock.
- **Threat model clarity**: microjail provides egress control, not escape prevention. This
  boundary MUST be stated wherever the tool's guarantees are described.

## Development Workflow

- **Test-first for gate logic**: Any new lock gate MUST have a test that demonstrates it
  blocks a workload when the condition is not met before implementation is merged.
- **Regression coverage for safety paths**: Changes to the lock/unlock flow MUST be
  accompanied by tests covering the affected path.
- **Gate failures are bugs, not features**: If a gate can be bypassed by normal usage, that
  is a defect to be fixed, not a flexibility to be documented.
- **Early and incremental delivery**: Implement the minimum gate set that is correct, then
  expand. Do not ship a gate that is advisory when it was designed to be blocking.

## Governance

This constitution supersedes all other guidance for this project. Any practice, convention,
or tool default that conflicts with these principles yields to the constitution.

**Amendment procedure**:
1. Propose the amendment in a pull request that modifies this file.
2. State the version bump type (MAJOR / MINOR / PATCH) and justify it.
3. Identify all templates and documentation affected and update them in the same PR.
4. A human reviewer MUST approve before merge.

**Versioning policy** (semantic versioning):
- MAJOR: Removes or redefines a principle in a backward-incompatible way.
- MINOR: Adds a new principle, section, or materially expands guidance.
- PATCH: Clarifications, wording improvements, typo fixes.

**Compliance review**: Every plan's Constitution Check section MUST be filled before
implementation begins. The review MUST be re-run after Phase 1 design is complete.

**Version**: 1.0.1 | **Ratified**: TODO(RATIFICATION_DATE): original adoption date unknown — set when first committed | **Last Amended**: 2026-06-01
