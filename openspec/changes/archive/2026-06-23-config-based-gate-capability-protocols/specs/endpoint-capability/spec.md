## MODIFIED Requirements

### Requirement: check reflects connection and reachability state
`WorkshopEndpointCapability.check(microjail)` MUST return `True` if and only if the Workshop tunnel connection (`<workshop>/microjail:<name>` → `<workshop>/system:<name>`) appears in `workshop connections` output. The check MUST NOT perform a TCP reachability probe; reachability is verified separately by `verify()`. If the tunnel connection is not present, `check()` MUST return `False`. `check()` MUST NOT raise.

#### Scenario: check returns False before provide
- **WHEN** `WorkshopEndpointCapability.check(microjail)` is called before `provide()` has been called
- **THEN** the return value is `False`

#### Scenario: check returns True after provide
- **WHEN** `WorkshopEndpointCapability.provide(microjail)` has completed successfully
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `True`

#### Scenario: check returns False after revoke
- **WHEN** `WorkshopEndpointCapability.revoke(microjail)` has completed
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `False`

#### Scenario: check returns False after workshop refresh
- **WHEN** `WorkshopEndpointCapability.provide(microjail)` has completed successfully
- **AND** `workshop refresh` is run externally
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `False`

This is expected: outgoing tunnel connections are not durable across refreshes. `ensure()` will call `provide()` again to reconnect before the workload starts.

#### Scenario: check returns False when workshop is not available
- **WHEN** `WorkshopEndpointCapability.check(microjail)` is called and the workshop container is not running
- **THEN** the return value is `False` and no exception is raised

#### Scenario: check does not perform a TCP probe
- **WHEN** the tunnel connection is present in `workshop connections`
- **AND** the host service at the resolved endpoint is unreachable (e.g. the upstream process has crashed)
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `True` (the check is config-state only; reachability is the responsibility of `verify()`)

## ADDED Requirements

### Requirement: verify reflects reachability state
`WorkshopEndpointCapability.verify(microjail)` MUST return `VerificationResult.VERIFIED` if a TCP connection to the resolved endpoint (`container_endpoint` if set, otherwise `host_endpoint`) succeeds from inside the workshop container. If the TCP connection fails, times out, or raises any exception (including `subprocess.CalledProcessError`, `subprocess.TimeoutExpired`, `ValueError`), `verify()` MUST return `VerificationResult.FAILED` rather than propagating the exception.

#### Scenario: verify returns VERIFIED when endpoint is reachable
- **WHEN** the host service at the resolved endpoint is reachable
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.VERIFIED`

#### Scenario: verify returns FAILED when endpoint is unreachable
- **WHEN** the host service at the resolved endpoint is not reachable (e.g. the upstream process has crashed or the port is closed)
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.FAILED`

#### Scenario: verify returns FAILED when tunnel is not connected
- **WHEN** the tunnel connection is not present in `workshop connections`
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.FAILED`

#### Scenario: verify does not propagate subprocess errors
- **WHEN** the underlying reachability probe raises `subprocess.CalledProcessError` or `subprocess.TimeoutExpired`
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.FAILED` and no exception is raised
