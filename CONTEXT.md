# Microjail

Microjail defines the language for configuring and applying secure execution environments for autonomous agents and other untrusted workloads.

## Language

**Microjail**:
The safety-first product that orchestrates Workshop and LXD mechanisms to establish, monitor, and maintain secure execution environments with fewer manual configuration errors.
_Avoid_: sandbox implementation, proxy implementation, container runtime

**Microjail instance**:
A configured per-project binding between a Workshop project, Workshop-backed execution environment, project path, and Lockdown.
_Avoid_: Microjail product, active lockdown

**Lockdown**:
A declarative security policy describing the capabilities that should be available and the gates that should hold for a workload. It is not a record of whether the environment is currently locked.
_Avoid_: locked state, active lockdown, runtime state

**Capability**:
Functionality or access intentionally made available to a workload that would otherwise be unavailable.
_Avoid_: permission, exception, restriction

**Gate**:
A security invariant that must hold for a workload by removing, limiting, or continuously enforcing against ambient access. Gates are always fatal when they cannot be established or stop holding.
_Avoid_: capability, permission, feature

**Network egress**:
Outbound network access from the workload to external network destinations. Network paths are authorized only when represented as declared Capabilities in the Lockdown.
_Avoid_: all network access, endpoint capability

**Capability application failure**:
A failure to establish or verify functionality or access that a Lockdown declared should be available to the workload. Capability application failures are collected so Microjail can report all missing capabilities together, then block workload launch by default.
_Avoid_: gate failure, runtime violation

**Gate application failure**:
A failure to establish or verify a restriction that a Lockdown declared must hold for the workload. Gate application failures are severe and stop policy application at the first failed gate.
_Avoid_: capability failure, runtime violation

**Capability policy violation**:
Runtime loss of functionality or access that a Lockdown declared should remain available to the workload, including failure to verify that the functionality or access still exists. Capability policy violations are warnings by default and can be configured as fatal.
_Avoid_: gate violation, setup failure

**Gate policy violation**:
Runtime loss of a restriction that a Lockdown declared must hold for the workload, including failure to verify that the restriction still holds. Gate policy violations are fatal because they can expose access that should be denied.
_Avoid_: capability violation, setup failure

**Workload**:
The command and process tree executed inside the Workshop environment under an applied Lockdown.
_Avoid_: Workshop container, microjail instance, host process

**Warden**:
The runtime supervisor for a workload running under an applied Lockdown. It monitors policy invariants and terminates the workload on violation, but never releases policy.
_Avoid_: unlocker, policy applier, cleanup manager
