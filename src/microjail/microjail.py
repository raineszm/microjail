"""The MicroJail configuration object and its on-disk persistence."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec

from microjail.adapters import workshop

# Needed at runtime by msgspec for struct field resolution.
from microjail.gates.base import Gate
from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import CapabilityError, GateError, Lockdown

if TYPE_CHECKING:
    from microjail.caps.base import Capability

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
        return msgspec.convert(obj, type=NetworkDrop)
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
        """Apply this microjail's lockdown policy."""
        self.ensure_workshop_ready()
        provided_caps: list[Capability] = []
        enforced_gates: list[Gate] = []

        try:
            for cap in self.lockdown.caps:
                self.ensure_capability(cap, provided_caps)

            for gate in self.lockdown.gates:
                self.ensure_gate(gate, enforced_gates)
        except Exception:
            self.release_applied(provided_caps, enforced_gates)
            raise

    def ensure_workshop_ready(self) -> None:
        """Verify the associated workshop is launched and ready."""
        info = workshop.info(self.name, project=self.project_path)
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

    def release(self) -> None:
        """Release this microjail's lockdown policy."""
        errors: list[Exception] = []

        for gate in reversed(self.lockdown.gates):
            try:
                gate.release(self)
            except Exception as exc:
                errors.append(exc)

        for cap in reversed(self.lockdown.caps):
            try:
                cap.revoke(self)
            except Exception as exc:
                errors.append(exc)

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
            except Exception as exc:
                errors.append(exc)

        for cap in reversed(provided_caps):
            try:
                cap.revoke(self)
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise ExceptionGroup("lockdown release failures", errors)

    def ensure_capability(
        self,
        cap: Capability,
        provided_caps: list[Capability],
    ) -> None:
        """check → provide if missing → verify for a single capability."""
        if not cap.check(self):
            provided_caps.append(cap)
            cap.provide(self)
            if not cap.check(self):
                raise CapabilityError(name=cap.name)

    def ensure_gate(
        self,
        gate: Gate,
        enforced_gates: list[Gate],
    ) -> None:
        """check → enforce if unsatisfied → verify for a single gate."""
        if not gate.check(self):
            enforced_gates.append(gate)
            gate.enforce(self)
            if not gate.check(self):
                raise GateError(name=gate.name)

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
