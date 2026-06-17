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

**Lockdown application**:
The act of applying a Lockdown to a Microjail instance: verifying the Workshop environment, establishing declared Capabilities, enforcing Gates, recording what changed, and reporting Capability application failures or Gate application failures without releasing the Lockdown unless the caller requested rollback.
_Avoid_: policy execution, sandbox setup, runtime lock state

**Capability**:
Functionality or access intentionally made available to a workload that would otherwise be unavailable. Capability names identify declared workload access within a Lockdown and must be unique across all Capability types in that Lockdown.
_Avoid_: permission, exception, restriction

**Capability declaration**:
A Lockdown entry stating that functionality or access should be available to a workload. A declaration is not proof that the functionality has been provisioned; provisioning happens during Lockdown application.
_Avoid_: provided capability, live capability, permission

**Unauthorized access**:
Functionality or access available to a workload that is not represented by a current Capability declaration in the Lockdown. Unauthorized access is more dangerous than missing declared access because it expands what the workload can reach beyond the reviewed policy.
_Avoid_: stale capability, extra permission

**Gate**:
A security invariant that must hold for a workload by removing, limiting, or continuously enforcing against ambient access. Gates are always fatal when they cannot be established or stop holding.
_Avoid_: capability, permission, feature

**Network egress**:
Outbound network access from the workload to external network destinations. Network paths are authorized only when represented as declared Capabilities in the Lockdown.
_Avoid_: all network access, endpoint capability

**Network-drop Gate**:
A Gate that prevents a workload from establishing network egress. It enforces that all outbound network paths are blocked by default, requiring specific Endpoint capabilities to authorize exceptions.
_Avoid_: network block, egress drop

**Readonly-config Gate**:
A Gate that prevents a workload from modifying the Microjail configuration that defines its own Lockdown.
_Avoid_: readonly-config capability, endpoint capability, config permission

**Capability application failure**:
A failure to establish or verify functionality or access that a Lockdown declared should be available to the workload. Capability application failures are collected so Microjail can report all missing capabilities together, then block workload launch by default.
_Avoid_: gate failure, runtime violation

**Gate application failure**:
A failure to establish or verify a restriction that a Lockdown declared must hold for the workload. Gate application failures are severe and stop policy application at the first failed gate.
_Avoid_: capability failure, runtime violation

**Capability policy violation**:
Runtime loss of functionality or access that a Lockdown declared should remain available to the workload, including failure to verify that the functionality or access still exists. Capability policy violations are fatal because the workload is operating outside its declared capability bounds.
_Avoid_: gate violation, setup failure

**Gate policy violation**:
Runtime loss of a restriction that a Lockdown declared must hold for the workload, including failure to verify that the restriction still holds. Gate policy violations are fatal because they can expose access that should be denied.
_Avoid_: capability violation, setup failure

**Workload**:
The command and process tree executed inside the Workshop environment under an applied Lockdown.
_Avoid_: Workshop container, microjail instance, host process

**Workload process handle**:
The host-side control handle (specifically a `subprocess.Popen` instance) representing the asynchronously executing Workload, used by the Warden or caller to monitor, communicate with, or terminate the Workload.
_Avoid_: Popen object, container process, background process

**Warden**:
The runtime supervisor for a workload running under an applied Lockdown. It monitors policy invariants and terminates the workload on violation, but never releases policy.
_Avoid_: unlocker, policy applier, cleanup manager

**Release**:
The act of revoking all applied Capabilities and releasing all enforced Gates from a Microjail instance, returning the environment to its baseline state. Unlike Destroy, Release does not stop running workloads or remove the Workshop environment.
_Avoid_: unlock (as a domain concept, though the CLI command is `unlock`), teardown

**Destroy**:
Explicit teardown of a microjail instance: stopping any running workload, releasing the Lockdown, and removing the Workshop environment. Requires user confirmation. Leaves the project directory on the host intact.
_Avoid_: unlock, remove, clean up

**Workshop adoption**:
The act of bringing an existing Workshop project under microjail management. Microjail reads the existing workshop.yaml, requires the user to declare which tunnels and connections become Capabilities in the Lockdown, and takes ownership of the file going forward. Pre-existing tunnels not represented in the Lockdown are treated as unauthorized.
_Avoid_: import, migration, takeover

**Endpoint capability**:
A declared Capability that authorizes a workload to reach a specific host service via a Workshop tunnel. Declared with `host_endpoint` (the host-side address the tunnel forwards from) and an optional `container_endpoint` (the address the workload sees inside the container; defaults to `host_endpoint`). The `name` field becomes the Workshop plug/slot identifier. Endpoint capabilities are the only authorized network paths through the network-egress Gate.
_Avoid_: tunnel permission, proxy exception, port forwarding
