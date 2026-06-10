"""The MicroJail configuration object and its on-disk persistence."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec

from microjail.adapters import lxc, workshop
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


@dataclass(frozen=True)
class LockApplicationResult:
    """Result of applying policy for the `lock` command."""

    capability_failures: list[CapabilityError]
    gates_enforced: int
    gate_failure: GateError | None = None


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
    name:
        Name of the associated workshop.
    project_path:
        Path to the workshop project that this microjail governs.
    lockdown:
        The policy applied while workloads execute.
    """

    name: str
    project_path: Path
    lockdown: Lockdown

    @property
    def config_dir(self) -> Path:
        return self.project_path / CONFIG_DIRNAME

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    def ensure(self) -> None:
        """Apply this microjail's lockdown policy for a workload launch."""
        self.ensure_for_run()

    def ensure_for_run(self) -> None:
        """Apply policy for `run`, rolling back if the workload will not start."""
        self.ensure_workshop_ready()
        provided_caps: list[Capability] = []
        enforced_gates: list[Gate] = []
        capability_errors: list[CapabilityError] = []

        try:
            for cap in self.lockdown.caps:
                try:
                    self.ensure_capability(cap, provided_caps)
                except CapabilityError as exc:
                    capability_errors.append(exc)

            if len(capability_errors) == 1:
                raise capability_errors[0]
            if capability_errors:
                raise ExceptionGroup(
                    "capability application failures", capability_errors
                )

            for gate in self.lockdown.gates:
                self.ensure_gate(gate, enforced_gates)
        except Exception:
            self.release_applied(provided_caps, enforced_gates)
            raise

    def ensure_for_lock(self) -> LockApplicationResult:
        """Apply policy for `lock`, leaving the safest reachable posture in place."""
        self.ensure_workshop_ready()
        provided_caps: list[Capability] = []
        enforced_gates: list[Gate] = []
        capability_errors: list[CapabilityError] = []

        for cap in self.lockdown.caps:
            try:
                self.ensure_capability(cap, provided_caps)
            except CapabilityError as exc:
                capability_errors.append(exc)

        for gate in self.lockdown.gates:
            try:
                self.ensure_gate(gate, enforced_gates)
            except GateError as exc:
                return LockApplicationResult(
                    capability_failures=capability_errors,
                    gates_enforced=len(enforced_gates),
                    gate_failure=exc,
                )

        return LockApplicationResult(
            capability_failures=capability_errors,
            gates_enforced=len(self.lockdown.gates),
        )

    def workshop_info(self) -> workshop.WorkshopInfo | None:
        """Return workshop info, or None if the workshop is not launched."""
        return workshop.info(self.name, project=self.project_path)

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
        return workshop.exec_(self.name, self.project_path, command, **kwargs)

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
        workshop.restore(self.name, project=self.project_path)

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

    def release_applied(
        self,
        provided_caps: list[Capability],
        enforced_gates: list[Gate],
    ) -> None:
        """Tear down only state that this ensure() call attempted to apply."""
        errors: list[Exception] = []

        for gate in reversed(enforced_gates):
            try:
                gate.release(self)
            except Exception:
                errors.append(GateReleaseError(name=gate.name))

        for cap in reversed(provided_caps):
            try:
                cap.revoke(self)
            except Exception:
                errors.append(CapabilityReleaseError(name=cap.name))

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    def ensure_capability(
        self,
        cap: Capability,
        provided_caps: list[Capability],
    ) -> None:
        """check → provide if missing → verify for a single capability."""
        try:
            if cap.check(self):
                return
            provided_caps.append(cap)
            cap.provide(self)
            if not cap.check(self):
                raise CapabilityError(name=cap.name)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(name=cap.name) from exc

    def ensure_gate(
        self,
        gate: Gate,
        enforced_gates: list[Gate],
    ) -> None:
        """check → enforce if unsatisfied → verify for a single gate."""
        try:
            if gate.check(self):
                return
            enforced_gates.append(gate)
            gate.enforce(self)
            if not gate.check(self):
                raise GateError(name=gate.name)
        except GateError:
            raise
        except Exception as exc:
            raise GateError(name=gate.name) from exc

    def save(self) -> None:
        """Persist this microjail to ``.microjail/config.yaml``."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes(msgspec.yaml.encode(self, enc_hook=enc_hook))

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
