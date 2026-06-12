import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from microjail.microjail import MicroJail


class GatePolicyViolation(Exception):
    """Raised when a gate policy violation is detected at runtime."""


class CapabilityPolicyViolation(Exception):
    """Raised when a fatal capability policy violation is detected at runtime."""


class Warden:
    """Runtime supervisor for executing workloads under an applied Lockdown."""

    def __init__(
        self,
        microjail: MicroJail,
        process: subprocess.Popen,
        interval: float = 1.0,
    ) -> None:
        self.microjail = microjail
        self.process = process
        self.interval = interval

    def supervise(self) -> int:
        """Supervise the workload process and block until it terminates."""
        while True:
            try:
                # Wait blocks up to interval seconds.
                # If the process terminates, wait() returns its exit code.
                exit_code = self.process.wait(timeout=self.interval)
                return exit_code
            except subprocess.TimeoutExpired:
                # The process is still running. Perform periodic checks.
                self.check_policies()

    def check_policies(self) -> None:
        """Inspect all active gates and capabilities."""
        for gate in self.microjail.lockdown.gates:
            if not gate.check(self.microjail):
                self.terminate_workload()
                raise GatePolicyViolation(f"Gate policy violation: {gate.name}")

        for cap in self.microjail.lockdown.caps:
            if not cap.check(self.microjail):
                if getattr(cap, "fatal", False):
                    self.terminate_workload()
                    raise CapabilityPolicyViolation(
                        f"Capability policy violation: {cap.name}"
                    )
                else:
                    import sys

                    print(
                        f"Warning: Capability policy violation: {cap.name}",
                        file=sys.stderr,
                    )

    def terminate_workload(self) -> None:
        """Terminate the workload process and escalate to container force stop if needed."""
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            from microjail.adapters import lxc

            container = self.microjail.container_name()
            project = self.microjail.lxd_project()
            lxc.stop_instance(container, project, force=True)
