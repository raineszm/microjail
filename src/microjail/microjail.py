"""The MicroJail configuration object and its on-disk persistence."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anyio.abc import Process

import anyio
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
    purge_path: str = "data"

    @property
    def config_dir(self) -> Path:
        return self.project_path / CONFIG_DIRNAME

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    async def workshop_info(self) -> workshop.WorkshopInfo | None:
        """Return workshop info, or None if the workshop is not launched."""
        return await workshop.info(self.name, project=self.project_path)

    async def ensure_workshop_ready(self) -> None:
        """Verify the associated workshop is launched and ready."""
        info = await self.workshop_info()
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

    async def exec_(self, command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """Execute *command* inside the associated workshop container."""
        return await workshop.exec_(self.name, self.project_path, command, **kwargs)

    async def popen(
        self,
        command: list[str],
        *,
        interactive: bool = False,
        **kwargs,
    ) -> Process:
        """Execute *command* inside the associated workshop container and return a Workload process handle."""
        return await workshop.popen(
            self.name,
            self.project_path,
            command,
            interactive=interactive,
            **kwargs,
        )

    async def container_name(self) -> str:
        """Return the LXD container name, raising if the workshop is not launched."""
        container = await workshop.get_container(self.name, project=self.project_path)
        if container is None:
            raise workshop.WorkshopNotLaunchedError(
                name=self.name, project=self.project_path
            )
        return container.name

    async def restore_workshop(self) -> None:
        """Restore the Workshop environment to its last launch/refresh point."""
        await workshop.restore(self.name, project=self.project_path)

    def lxd_project(self) -> str:
        """Return the workshop LXD project name."""
        return workshop.lxd_project()

    async def lxc_instance(self) -> lxc.InstanceInfo:
        """Return LXD instance information for this workshop's container."""
        c_name = await self.container_name()
        return await lxc.get_instance(c_name, project=self.lxd_project())

    async def get_network_bridge_gateway(self) -> str:
        """Find the host gateway IP of the bridge network attached to this workshop."""
        instance = await self.lxc_instance()
        for dev_config in instance.devices.values():
            if dev_config.get("type") == "nic" and "network" in dev_config:
                network_name = str(dev_config["network"])
                from microjail.adapters import lxc as lxc_adapter

                net_info = await lxc_adapter.get_network(network_name)
                ipv4_cidr = net_info.config.ipv4_address
                if not ipv4_cidr:
                    raise ValueError(
                        f"no IPv4 address configured on network {network_name}"
                    )
                return ipv4_cidr.split("/")[0]
        raise ValueError("No NIC device found for the workshop container")

    async def profile_devices(self) -> dict[str, dict[str, object]]:
        """Return devices contributed by profiles attached to this instance."""
        devices: dict[str, dict[str, object]] = {}
        instance = await self.lxc_instance()
        for profile in instance.profiles:
            devices.update(
                await lxc.get_profile_devices(profile, project=self.lxd_project())
            )
        return devices

    async def remove_device(self, device: str) -> None:
        """Remove *device* from the workshop container."""
        c_name = await self.container_name()
        await lxc.remove_device(c_name, device, project=self.lxd_project())

    async def add_device(self, device: str, config: dict[str, object]) -> None:
        """Add *device* with *config* to the workshop container."""
        c_name = await self.container_name()
        await lxc.add_device(c_name, device, config, project=self.lxd_project())

    async def release(self) -> None:
        """Release this microjail's lockdown policy."""
        errors: list[Exception] = []

        async def release_gate(gate):
            try:
                await gate.release(self)
            except Exception:
                errors.append(GateReleaseError(name=gate.name))

        async def revoke_cap(cap):
            try:
                await cap.revoke(self)
            except Exception:
                errors.append(CapabilityReleaseError(name=cap.name))

        async with anyio.create_task_group() as tg:
            for gate in reversed(self.lockdown.gates):
                tg.start_soon(release_gate, gate)

        async with anyio.create_task_group() as tg:
            for cap in reversed(self.lockdown.caps):
                tg.start_soon(revoke_cap, cap)

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    async def ensure(self, intent: ApplicationIntent) -> ApplicationResult:
        """Ensure this microjail's lockdown holds for the requested intent."""
        await self.ensure_workshop_ready()
        provided_capabilities: list[Capability] = []
        enforced_gates: list[Gate] = []
        capability_failures: list[CapabilityError] = []

        async def run_cap(cap):
            try:
                await _ensure_capability(self, cap, provided_capabilities)
            except CapabilityError as exc:
                capability_failures.append(exc)

        async with anyio.create_task_group() as tg:
            for cap in self.lockdown.caps:
                tg.start_soon(run_cap, cap)

        if capability_failures and intent is ApplicationIntent.RUN:
            rollback_failures = await _rollback(
                self, provided_capabilities, enforced_gates
            )
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
                await _ensure_gate(self, gate, enforced_gates)
            except GateError as exc:
                rollback_failures: list[RollbackFailure] = []
                if intent is ApplicationIntent.RUN:
                    rollback_failures = await _rollback(
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

    async def destroy(
        self,
        *,
        delete_project: bool = False,
        echo: Callable[[str], None] | None = None,
    ) -> None:
        """Tear down workshop infrastructure and purge data.

        If delete_project is True, delete the entire project directory.
        """
        import shutil

        while True:
            info = await workshop.info(self.name, self.project_path)
            if not info:
                break
            if info.status == "pending":
                if echo:
                    echo("Workshop is pending, waiting...")
                await anyio.sleep(2)
                continue
            elif info.status == "off":
                if echo:
                    echo("Workshop is off, starting before removal...")
                await workshop.start(self.name, self.project_path)
                break
            else:
                break

        await workshop.remove(self.name, self.project_path)

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
    async def init(
        cls,
        name: str,
        project_path: Path,
        sdks: list[str] | None = None,
        base: str | None = None,
    ) -> MicroJail:
        """Initialize a new microjail: create Workshop and persist config.

        Raises
        ------
        WorkshopExistsError:
            If a Workshop with *name* already exists at *project_path*.
        """
        await workshop.init(name, project=project_path, sdks=sdks, base=base)
        config = cls(name=name, project_path=project_path, lockdown=Lockdown.default())
        config.save()
        if config.purge_path:
            (project_path / config.purge_path).mkdir(parents=True, exist_ok=True)
        return config


async def _ensure_capability(
    microjail: MicroJail,
    cap: Capability,
    provided_capabilities: list[Capability],
) -> None:
    """check → provide if missing → verify for one Capability."""
    try:
        if await cap.check(microjail):
            return
        provided_capabilities.append(cap)
        await cap.provide(microjail)
        if not await cap.check(microjail):
            raise CapabilityError(name=cap.name)
    except CapabilityError:
        raise
    except Exception as exc:
        raise CapabilityError(name=cap.name) from exc


async def _ensure_gate(
    microjail: MicroJail,
    gate: Gate,
    enforced_gates: list[Gate],
) -> None:
    """check → enforce if unsatisfied → verify for one Gate."""
    try:
        if await gate.check(microjail):
            return
        enforced_gates.append(gate)
        await gate.enforce(microjail)
        if not await gate.check(microjail):
            raise GateError(name=gate.name)
    except GateError:
        raise
    except Exception as exc:
        raise GateError(name=gate.name) from exc


async def _rollback(
    microjail: MicroJail,
    provided_capabilities: list[Capability],
    enforced_gates: list[Gate],
) -> list[RollbackFailure]:
    """Release only state touched by this lockdown ensure call."""
    failures: list[RollbackFailure] = []

    async def release_gate(gate):
        try:
            await gate.release(microjail)
        except Exception:
            failures.append(GateReleaseError(name=gate.name))

    async def revoke_cap(cap):
        try:
            await cap.revoke(microjail)
        except Exception:
            failures.append(CapabilityReleaseError(name=cap.name))

    async with anyio.create_task_group() as tg:
        for gate in reversed(enforced_gates):
            tg.start_soon(release_gate, gate)

    async with anyio.create_task_group() as tg:
        for cap in reversed(provided_capabilities):
            tg.start_soon(revoke_cap, cap)

    return failures
