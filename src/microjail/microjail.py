"""The MicroJail configuration object and its on-disk persistence."""

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec

from microjail.adapters import lxc
from microjail.adapters.workshop import (
    CommandExecutor,
    Workshop,
    WorkshopConfig,
    WorkshopInfo,
    WorkshopNotLaunchedError,
)
from microjail.caps.base import Capability
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.exceptions import MicrojailError
from microjail.gates.base import Gate
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import (
    CapabilityError,
    CapabilityReleaseError,
    GateError,
    GateReleaseError,
    Lockdown,
)

TaggedGate = NetworkDrop | ReadonlyConfig
TaggedCapability = WorkshopEndpointCapability

if TYPE_CHECKING:
    from collections.abc import Callable

    from microjail.adapters.workshop import TunnelBatch

CONFIG_DIRNAME = ".microjail"
CONFIG_FILENAME = "config.yaml"


@dataclass(frozen=True)
class ConfigNotFoundError(MicrojailError):
    """Raised when no microjail config exists for a project."""

    project_path: Path


@dataclass(frozen=True)
class WorkshopNotReadyError(MicrojailError):
    """Raised when a workshop exists but is not ready for lockdown."""

    name: str
    project: Path
    status: str


class ApplicationIntent(StrEnum):
    LOCK = "lock"
    RUN = "run"


class ApplicationStatus(StrEnum):
    SUCCESS = "success"
    CAPABILITY_APPLICATION_FAILURE = "capability-application-failure"
    GATE_APPLICATION_FAILURE = "gate-application-failure"


RollbackFailure = CapabilityReleaseError | GateReleaseError


@dataclass(frozen=True)
class ApplicationResult:
    intent: ApplicationIntent
    status: ApplicationStatus
    capability_failures: tuple[CapabilityError, ...] = ()
    gate_failure: GateError | None = None
    rollback_failures: tuple[RollbackFailure, ...] = ()
    provided_capabilities: tuple[Capability, ...] = ()
    enforced_gates: tuple[Gate, ...] = ()
    gates_enforced: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status is ApplicationStatus.SUCCESS


def enc_hook(obj: object) -> object:
    """Serialize types msgspec does not handle natively."""
    if isinstance(obj, Path):
        return str(obj)
    raise NotImplementedError(f"cannot encode object of type {type(obj).__name__}")


def dec_hook(expected: type, obj: object) -> object:
    """Deserialize types msgspec does not handle natively."""
    if expected is Path:
        return Path(str(obj))
    if expected is Gate:
        return msgspec.convert(obj, type=TaggedGate)
    if expected is Capability:
        return msgspec.convert(obj, type=TaggedCapability)
    raise NotImplementedError(f"cannot decode object of type {expected.__name__}")


class MicroJailConfig(msgspec.Struct, omit_defaults=True):
    """DTO form of a microjail, suitable for YAML serialization.

    Holds only the fields that belong in configuration; the workshop's executor
    is a runtime dependency that is injected at construction time, not
    serialized.
    """

    workshop: WorkshopConfig
    lockdown: Lockdown
    purge_path: str = "data"


@dataclass(frozen=True)
class EndpointCapabilityInfo:
    """Read-only view of an endpoint capability for status display."""

    name: str
    host_endpoint: str
    container_endpoint: str
    fatal: bool


@dataclass(frozen=True)
class MicroJailStatus:
    """Read-only snapshot of microjail and workshop state."""

    workshop_name: str
    workshop_status: str
    capabilities: tuple[str, ...]
    gates: tuple[str, ...]
    connections: tuple[tuple[str, str], ...]
    endpoint_capabilities: tuple[EndpointCapabilityInfo, ...] = ()


@dataclass(frozen=True)
class ValidateError:
    """A single validation error found during ``microjail validate``."""

    kind: str
    message: str
    hint: str


@dataclass(frozen=True)
class PreLaunchVerifyResult:
    non_fatal_capability_failures: tuple[str, ...]
    unsupported_verifications: tuple[str, ...] = ()


@dataclass
class MicroJail:
    """Runtime microjail: a per-project binding between a workshop, a Lockdown,
    and a purge path.

    Constructed directly for tests and ad-hoc use, or via
    :meth:`from_config` from a :class:`MicroJailConfig` loaded from disk.
    Use :meth:`to_config` to produce the DTO form for :meth:`save`.
    """

    workshop: Workshop
    lockdown: Lockdown
    purge_path: str = "data"

    def to_config(self) -> MicroJailConfig:
        """Return the serializable DTO form of this microjail.

        The workshop's executor is dropped; it is a runtime dependency, not
        configuration.
        """
        return MicroJailConfig(
            workshop=self.workshop.to_config(),
            lockdown=self.lockdown,
            purge_path=self.purge_path,
        )

    @classmethod
    def from_config(
        cls,
        config: MicroJailConfig,
        executor: CommandExecutor | None = None,
    ) -> MicroJail:
        """Construct a runtime microjail from a ``MicroJailConfig`` DTO.

        The executor is injected into the inner workshop at construction
        time; it never appears in the DTO or in on-disk configuration.
        """
        return cls(
            workshop=Workshop.from_config(config.workshop, executor),
            lockdown=config.lockdown,
            purge_path=config.purge_path,
        )

    @property
    def name(self) -> str:
        return self.workshop.name

    @property
    def project_path(self) -> Path:
        return self.workshop.project

    @property
    def config_dir(self) -> Path:
        return self.project_path / CONFIG_DIRNAME

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    def workshop_info(self) -> WorkshopInfo | None:
        """Return workshop info, or None if the workshop is not launched."""
        return self.workshop.info()

    def status(self) -> MicroJailStatus:
        """Return a snapshot of the current microjail and workshop state."""
        info = self.workshop_info()
        try:
            connections = self.workshop.tunnel.connections()
        except subprocess.CalledProcessError, OSError:
            connections = []
        endpoint_caps = tuple(
            EndpointCapabilityInfo(
                name=cap.name,
                host_endpoint=cap.host_endpoint,
                container_endpoint=cap.resolved_endpoint,
                fatal=cap.fatal,
            )
            for cap in self.lockdown.caps
            if isinstance(cap, WorkshopEndpointCapability)
        )
        return MicroJailStatus(
            workshop_name=self.name,
            workshop_status=info.status if info else "unavailable",
            capabilities=tuple(cap.name for cap in self.lockdown.caps),
            gates=tuple(gate.name for gate in self.lockdown.gates),
            connections=tuple(connections),
            endpoint_capabilities=endpoint_caps,
        )

    def validate(self) -> list[ValidateError]:
        """Validate the lockdown configuration without applying policy.

        Checks schema conformance (loaded config) and semantic rules:
        duplicate capability names, endpoint name format, endpoint address format.
        """
        errors: list[ValidateError] = []

        # Check for duplicate capability names
        seen: set[str] = set()
        for cap in self.lockdown.caps:
            if cap.name in seen:
                errors.append(
                    ValidateError(
                        kind="duplicate_name",
                        message=f"duplicate capability name '{cap.name}' in config",
                        hint="Remove or rename one of the duplicate capabilities",
                    )
                )
            seen.add(cap.name)

        # Validate endpoint capabilities
        from microjail.caps.endpoint import (
            WorkshopEndpointCapability,
            validate_endpoint_address,
            validate_endpoint_name,
        )

        for cap in self.lockdown.caps:
            if not isinstance(cap, WorkshopEndpointCapability):
                continue

            name_err = validate_endpoint_name(cap.name)
            if name_err:
                errors.append(
                    ValidateError(
                        kind="endpoint_name",
                        message=name_err,
                        hint="Use a name starting with a letter, followed by letters, digits, or hyphens",
                    )
                )

            addr_err = validate_endpoint_address(cap.host_endpoint)
            if addr_err:
                errors.append(
                    ValidateError(
                        kind="endpoint_syntax",
                        message=addr_err,
                        hint="Use HOST:PORT format (e.g., 127.0.0.1:8080)",
                    )
                )

        return errors

    def ensure_workshop_ready(self) -> None:
        """Verify the associated workshop is launched and ready."""
        info = self.workshop_info()
        if info is None:
            raise WorkshopNotLaunchedError(name=self.name, project=self.project_path)
        if info.status != "ready":
            raise WorkshopNotReadyError(
                name=self.name,
                project=self.project_path,
                status=info.status,
            )

    def exec_(self, command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """Execute *command* inside the associated workshop container."""
        return self.workshop.exec_(command, **kwargs)

    def popen(
        self,
        command: list[str],
        *,
        interactive: bool = False,
        **kwargs,
    ) -> subprocess.Popen:
        """Execute *command* inside the associated workshop container and return a Workload process handle."""
        return self.workshop.popen(command, interactive=interactive, **kwargs)

    def shell(self, **kwargs) -> subprocess.Popen:
        """Open the associated workshop's default interactive shell and return a process handle."""
        return self.workshop.shell(**kwargs)

    def container_name(self) -> str:
        """Return the LXD container name, raising if the workshop is not launched."""
        container = self.workshop.get_container()
        if container is None:
            raise WorkshopNotLaunchedError(name=self.name, project=self.project_path)
        return container.name

    def restore_workshop(self) -> None:
        """Restore the Workshop environment to its last launch/refresh point."""
        self.workshop.restore()

    def lxd_project(self) -> str:
        """Return the workshop LXD project name."""
        return self.workshop.lxd_project

    def lxc_instance(self) -> lxc.InstanceInfo:
        """Return LXD instance information for this workshop's container."""
        return lxc.get_instance(self.container_name(), project=self.lxd_project())

    def profile_devices(self) -> dict[str, dict[str, object]]:
        """Return devices contributed by profiles attached to this instance."""
        devices: dict[str, dict[str, object]] = {}
        instance = self.lxc_instance()
        for profile in instance.profiles:
            devices.update(lxc.get_profile_devices(profile, project=self.lxd_project()))
        return devices

    def remove_device(self, device: str) -> None:
        """Remove *device* from the workshop container."""
        lxc.remove_device(self.container_name(), device, project=self.lxd_project())

    def add_device(self, device: str, config: dict[str, object]) -> None:
        """Add *device* with *config* to the workshop container."""
        lxc.add_device(
            self.container_name(), device, config, project=self.lxd_project()
        )

    def attach_network(self, network: str) -> None:
        """Attach *network* to the workshop container with a default device name.

        Used by the network-egress gate as a fallback when removed nics
        cannot be reconstructed from recorded state or the container's
        profiles. The network is resolved in the default project; the
        container reference is scoped to the workshop project.
        """
        lxc.attach_network(network, self.container_name(), project=self.lxd_project())

    def release(self) -> None:
        """Release this microjail's lockdown policy."""
        errors: list[Exception] = []

        for gate in reversed(self.lockdown.gates):
            try:
                gate.release(self)
            except Exception:
                errors.append(GateReleaseError(name=gate.name))

        with self.workshop.batch() as batch:
            for cap in reversed(self.lockdown.caps):
                try:
                    cap.revoke(self, batch=batch)
                except Exception:
                    errors.append(CapabilityReleaseError(name=cap.name))
            try:
                batch.flush()
            except Exception:
                errors.append(CapabilityReleaseError(name="workshop-refresh"))

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    def _reconcile_endpoint_declarations(self) -> list[CapabilityError]:
        """Remove Microjail-owned Workshop endpoint declarations not in the Lockdown.

        Before providing declared capabilities, clean up stale endpoint plug/slot
        declarations from the Microjail SDK YAML that are not represented by a
        declared Endpoint Capability in the Lockdown.

        Stale declaration removal is not rolled back on later failures.
        Returns capability errors for any removals that failed.
        """
        from microjail.adapters.workshop import (
            MicrojailSdkConfigError,
            read_microjail_sdk,
        )

        try:
            sdk = read_microjail_sdk(self.project_path)
        except MicrojailSdkConfigError:
            # No microjail SDK file — no stale declarations to clean
            return []
        except Exception:
            return []

        declared_names: set[str] = set()
        for cap in self.lockdown.caps:
            if isinstance(cap, WorkshopEndpointCapability):
                declared_names.add(cap.name)

        failures: list[CapabilityError] = []
        t = self.workshop.tunnel

        for plug_name in list(sdk.plugs):
            if plug_name not in declared_names:
                try:
                    remaining = t.remove_plug(plug_name)
                    t.remove_slot(plug_name, remove_sdk=not remaining)
                except Exception:
                    failures.append(CapabilityError(name=plug_name))

        return failures

    def ensure(self, intent: ApplicationIntent) -> ApplicationResult:
        """Ensure this microjail's lockdown holds for the requested intent."""
        self.ensure_workshop_ready()
        provided_capabilities: list[Capability] = []
        enforced_gates: list[Gate] = []
        capability_failures: list[CapabilityError] = []

        # Reconcile endpoint declarations before providing capabilities.
        # Stale cleanup failures block gate enforcement (unlike normal
        # capability failures, which only block gates for RUN intent).
        stale_failures = self._reconcile_endpoint_declarations()
        capability_failures.extend(stale_failures)

        if stale_failures:
            return ApplicationResult(
                intent=intent,
                status=ApplicationStatus.CAPABILITY_APPLICATION_FAILURE,
                capability_failures=tuple(capability_failures),
            )

        with self.workshop.batch() as batch:
            for cap in self.lockdown.caps:
                try:
                    _ensure_capability(self, cap, provided_capabilities, batch=batch)
                except CapabilityError as exc:
                    capability_failures.append(exc)
            try:
                batch.flush()
            except Exception:
                capability_failures.append(CapabilityError(name="workshop-refresh"))

        if capability_failures and intent is ApplicationIntent.RUN:
            rollback_failures = _rollback(self, provided_capabilities, enforced_gates)
            return ApplicationResult(
                intent=intent,
                status=ApplicationStatus.CAPABILITY_APPLICATION_FAILURE,
                capability_failures=tuple(capability_failures),
                rollback_failures=tuple(rollback_failures),
                provided_capabilities=tuple(provided_capabilities),
                enforced_gates=tuple(enforced_gates),
            )

        for gate in self.lockdown.gates:
            try:
                _ensure_gate(self, gate, enforced_gates)
            except GateError as exc:
                rollback_failures: list[RollbackFailure] = []
                if intent is ApplicationIntent.RUN:
                    rollback_failures = _rollback(
                        self, provided_capabilities, enforced_gates
                    )
                return ApplicationResult(
                    intent=intent,
                    status=ApplicationStatus.GATE_APPLICATION_FAILURE,
                    capability_failures=tuple(capability_failures),
                    gate_failure=exc,
                    rollback_failures=tuple(rollback_failures),
                    provided_capabilities=tuple(provided_capabilities),
                    enforced_gates=tuple(enforced_gates),
                    gates_enforced=len(enforced_gates),
                )

        if capability_failures:
            return ApplicationResult(
                intent=intent,
                status=ApplicationStatus.CAPABILITY_APPLICATION_FAILURE,
                capability_failures=tuple(capability_failures),
                provided_capabilities=tuple(provided_capabilities),
                enforced_gates=tuple(enforced_gates),
                gates_enforced=len(self.lockdown.gates),
            )

        return ApplicationResult(
            intent=intent,
            status=ApplicationStatus.SUCCESS,
            provided_capabilities=tuple(provided_capabilities),
            enforced_gates=tuple(enforced_gates),
            gates_enforced=len(self.lockdown.gates),
        )

    def pre_launch_verify(self) -> PreLaunchVerifyResult:
        """Perform behavioral verification of all gates and capabilities."""
        from microjail.gates.base import VerificationResult

        def _to_result(res: object) -> VerificationResult:
            from typing import cast

            if res is True:
                return VerificationResult.VERIFIED
            if res is False:
                return VerificationResult.FAILED
            return cast("VerificationResult", res)

        unsupported_verifications: list[str] = []

        for gate in self.lockdown.gates:
            res = _to_result(gate.verify(self))
            if res == VerificationResult.FAILED:
                raise GateError(
                    name=gate.name,
                    unsupported_verifications=tuple(unsupported_verifications),
                )
            elif res == VerificationResult.UNSUPPORTED:
                unsupported_verifications.append(gate.name)

        non_fatal_failures: list[str] = []
        for cap in self.lockdown.caps:
            res = _to_result(cap.verify(self))
            if res == VerificationResult.FAILED:
                if getattr(cap, "fatal", False):
                    raise CapabilityError(
                        name=cap.name,
                        non_fatal_failures=tuple(non_fatal_failures),
                        unsupported_verifications=tuple(unsupported_verifications),
                    )
                else:
                    non_fatal_failures.append(cap.name)
            elif res == VerificationResult.UNSUPPORTED:
                unsupported_verifications.append(cap.name)

        return PreLaunchVerifyResult(
            non_fatal_capability_failures=tuple(non_fatal_failures),
            unsupported_verifications=tuple(unsupported_verifications),
        )

    def save(self) -> None:
        """Persist this microjail to ``.microjail/config.yaml``."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes(
            msgspec.yaml.encode(self.to_config(), enc_hook=enc_hook)
        )

    def destroy(
        self,
        *,
        delete_project: bool = False,
        echo: Callable[[str], None] | None = None,
    ) -> None:
        """Tear down workshop infrastructure and purge data.

        If delete_project is True, delete the entire project directory.
        """
        import shutil
        import time

        while True:
            info = self.workshop.info()
            if not info:
                break
            if info.status == "pending":
                if echo:
                    echo("Workshop is pending, waiting...")
                time.sleep(2)
                continue
            elif info.status == "off":
                if echo:
                    echo("Workshop is off, starting before removal...")
                self.workshop.start()
                break
            else:
                break

        self.workshop.remove()

        if delete_project:
            shutil.rmtree(self.project_path)
        elif self.purge_path:
            purge_dir = self.project_path / self.purge_path
            if purge_dir.exists():
                shutil.rmtree(purge_dir)

    @classmethod
    def load(
        cls, project_path: Path, executor: CommandExecutor | None = None
    ) -> MicroJail:
        """Load the microjail config stored under ``project_path``.

        Raises
        ------
        ConfigNotFoundError:
            If no ``.microjail/config.yaml`` exists for the project.
        """
        config_path = project_path / CONFIG_DIRNAME / CONFIG_FILENAME
        try:
            raw = config_path.read_bytes()
        except FileNotFoundError as exc:
            raise ConfigNotFoundError(project_path=project_path) from exc

        config = msgspec.yaml.decode(raw, type=MicroJailConfig, dec_hook=dec_hook)
        return cls.from_config(config, executor)

    @classmethod
    def init(
        cls,
        name: str,
        project_path: Path,
        sdks: list[str] | None = None,
        base: str | None = None,
        executor: CommandExecutor | None = None,
    ) -> MicroJail:
        Workshop.init(
            name, project=project_path, sdks=sdks, base=base, executor=executor
        )
        config = cls(
            workshop=Workshop(name=name, project=project_path, executor=executor),
            lockdown=Lockdown.default(),
        )
        config.save()
        if config.purge_path:
            (project_path / config.purge_path).mkdir(parents=True, exist_ok=True)
        return config


def _ensure_capability(
    microjail: MicroJail,
    cap: Capability,
    provided_capabilities: list[Capability],
    batch: TunnelBatch | None = None,
) -> None:
    """check → provide if missing → verify for one Capability.

    When *batch* is provided, the post-provide verification check is
    skipped because the tunnel won't be connected until batch flush.
    """
    try:
        if cap.check(microjail):
            return
        provided_capabilities.append(cap)
        cap.provide(microjail, batch=batch)
        if batch is None and not cap.check(microjail):
            raise CapabilityError(name=cap.name)
    except CapabilityError:
        raise
    except Exception as exc:
        raise CapabilityError(name=cap.name) from exc


def _ensure_gate(
    microjail: MicroJail,
    gate: Gate,
    enforced_gates: list[Gate],
) -> None:
    """check → enforce if unsatisfied → verify for one Gate."""
    try:
        if gate.check(microjail):
            return
        enforced_gates.append(gate)
        gate.enforce(microjail)
        if not gate.check(microjail):
            raise GateError(name=gate.name)
    except GateError:
        raise
    except Exception as exc:
        raise GateError(name=gate.name) from exc


def _rollback(
    microjail: MicroJail,
    provided_capabilities: list[Capability],
    enforced_gates: list[Gate],
) -> list[RollbackFailure]:
    """Release only state touched by this lockdown ensure call."""
    failures: list[RollbackFailure] = []

    for gate in reversed(enforced_gates):
        try:
            gate.release(microjail)
        except Exception:
            failures.append(GateReleaseError(name=gate.name))

    for cap in reversed(provided_capabilities):
        try:
            cap.revoke(microjail)
        except Exception:
            failures.append(CapabilityReleaseError(name=cap.name))

    return failures
