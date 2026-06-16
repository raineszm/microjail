"""The MicroJail configuration object and its on-disk persistence."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec

from microjail.adapters import lxc, workshop
from microjail.adapters.workshop import Workshop
from microjail.caps.base import Capability
from microjail.caps.endpoint import WorkshopEndpointCapability
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
    import subprocess
    from collections.abc import Callable

CONFIG_DIRNAME = ".microjail"
CONFIG_FILENAME = "config.yaml"


@dataclass(frozen=True)
class ConfigNotFoundError(Exception):
    """Raised when no microjail config exists for a project."""

    project_path: Path


@dataclass(frozen=True)
class WorkshopNotReadyError(Exception):
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


class MicroJail(msgspec.Struct):
    """Configuration for a single microjail.
    Parameters
    ----------
    workshop:
        The workshop instance this microjail governs.
    lockdown:
        The policy applied while workloads execute.
    """

    workshop: Workshop
    lockdown: Lockdown
    purge_path: str = "data"

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

    def workshop_info(self) -> workshop.WorkshopInfo | None:
        """Return workshop info, or None if the workshop is not launched."""
        return self.workshop.info()

    def ensure_workshop_ready(self) -> None:
        """Verify the associated workshop is launched and ready."""
        info = self.workshop_info()
        if info is None:
            raise workshop.WorkshopNotLaunchedError(
                name=self.name, project=self.project_path
            )
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

    def container_name(self) -> str:
        """Return the LXD container name, raising if the workshop is not launched."""
        container = workshop.get_container(self.name, project=self.project_path)
        if container is None:
            raise workshop.WorkshopNotLaunchedError(
                name=self.name, project=self.project_path
            )
        return container.name

    def restore_workshop(self) -> None:
        """Restore the Workshop environment to its last launch/refresh point."""
        self.workshop.restore()

    def lxd_project(self) -> str:
        """Return the workshop LXD project name."""
        return workshop.lxd_project()

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

    def release(self) -> None:
        """Release this microjail's lockdown policy."""
        errors: list[Exception] = []

        for gate in reversed(self.lockdown.gates):
            try:
                gate.release(self)
            except Exception:
                errors.append(GateReleaseError(name=gate.name))

        for cap in reversed(self.lockdown.caps):
            try:
                cap.revoke(self)
            except Exception:
                errors.append(CapabilityReleaseError(name=cap.name))

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    def ensure(self, intent: ApplicationIntent) -> ApplicationResult:
        """Ensure this microjail's lockdown holds for the requested intent."""
        self.ensure_workshop_ready()
        provided_capabilities: list[Capability] = []
        enforced_gates: list[Gate] = []
        capability_failures: list[CapabilityError] = []

        for cap in self.lockdown.caps:
            try:
                _ensure_capability(self, cap, provided_capabilities)
            except CapabilityError as exc:
                capability_failures.append(exc)

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

    def save(self) -> None:
        """Persist this microjail to ``.microjail/config.yaml``."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes(msgspec.yaml.encode(self, enc_hook=enc_hook))

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
    def load(cls, project_path: Path) -> MicroJail:
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

        return msgspec.yaml.decode(raw, type=cls, dec_hook=dec_hook)

    @classmethod
    def init(
        cls,
        name: str,
        project_path: Path,
        sdks: list[str] | None = None,
        base: str | None = None,
    ) -> MicroJail:
        workshop.init(name, project=project_path, sdks=sdks, base=base)
        config = cls(
            workshop=Workshop(name=name, project=project_path),
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
) -> None:
    """check → provide if missing → verify for one Capability."""
    try:
        if cap.check(microjail):
            return
        provided_capabilities.append(cap)
        cap.provide(microjail)
        if not cap.check(microjail):
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
