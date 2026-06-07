"""Reusable marks to gate test execution"""

import shutil

import pytest


def requires_command(command: str):
    return pytest.mark.skipif(
        shutil.which(command) is None,
        reason=f"{command} not installed",
    )


def requires_lxd():
    return pytest.mark.lxd(requires_command("lxc"))


def requires_workshop():
    return pytest.mark.workshop(requires_command("workshop"))
