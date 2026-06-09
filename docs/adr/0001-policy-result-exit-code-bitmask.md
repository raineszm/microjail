# Use bitmask exit codes for policy results

Microjail uses bitmask exit codes for its own policy results while preserving workload exit-code passthrough when a workload runs without fatal policy failure. The high `0x40` marker distinguishes Microjail policy outcomes from generic command failures, and capability/gate/workload plus phase bits let callers classify incomplete locks, gate failures, workload termination blockers, runtime violations, and release failures without parsing output.

## Considered Options

- Plain sequential codes such as `10`, `11`, `12`, `13` — simpler, but leaves no room to group related policy outcomes.
- Fully namespaced Microjail exits with no workload passthrough — avoids numeric collisions, but makes `microjail run` worse as a command wrapper.

## Consequences

Workload exit codes can numerically collide with Microjail policy codes. Callers that need to distinguish them must use command context: a Microjail policy code means policy failed before or during supervision; otherwise `microjail run` passes through the workload's exit code.
