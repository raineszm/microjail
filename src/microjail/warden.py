from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from anyio.abc import Process

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
        process: Process,
        interval: float = 1.0,
    ) -> None:
        self.microjail = microjail
        self.process = process
        self.interval = interval

    async def supervise(self) -> int | None:
        """Supervise the workload process and block until it terminates."""
        exit_code = None

        async def wait_process():
            nonlocal exit_code
            exit_code = await self.process.wait()
            tg.cancel_scope.cancel()

        async def supervise_loop():
            while True:
                await anyio.sleep(self.interval)
                await self.check_policies()

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(wait_process)
                tg.start_soon(supervise_loop)
        except ExceptionGroup as eg:
            policy_exc, other_exc = eg.split(
                (GatePolicyViolation, CapabilityPolicyViolation)
            )
            if policy_exc is not None:
                policy = policy_exc.exceptions[0]
                if other_exc is not None:
                    raise ExceptionGroup(
                        "warden errors",
                        [policy, *other_exc.exceptions],
                    ) from None
                raise policy from None
            raise

        return exit_code

    async def check_policies(self) -> None:
        """Inspect all active gates and capabilities."""
        for gate in self.microjail.lockdown.gates:
            if not await gate.check(self.microjail):
                await self.terminate_workload()
                raise GatePolicyViolation(f"Gate policy violation: {gate.name}")

        for cap in self.microjail.lockdown.caps:
            if not await cap.check(self.microjail):
                if getattr(cap, "fatal", False):
                    await self.terminate_workload()
                    raise CapabilityPolicyViolation(
                        f"Capability policy violation: {cap.name}"
                    )
                else:
                    import sys

                    print(
                        f"Warning: Capability policy violation: {cap.name}",
                        file=sys.stderr,
                    )

    async def terminate_workload(self) -> None:
        """Terminate the workload process and escalate to container force stop if needed."""
        self.process.terminate()
        try:
            with anyio.fail_after(2):
                await self.process.wait()
        except TimeoutError:
            from microjail.adapters import lxc

            container = await self.microjail.container_name()
            project = self.microjail.lxd_project()
            await lxc.stop_instance(container, project, force=True)
