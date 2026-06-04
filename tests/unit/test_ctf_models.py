"""Unit tests for ctf.models."""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ctf.models import Secret, TestRun, TestRunConfig


def test_secret_fields() -> None:
    """Secret stores name and value and is immutable."""
    s = Secret(name="filesystem", value="abc")
    assert s.name == "filesystem"
    assert s.value == "abc"
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.name = "other"  # type: ignore[misc]


def test_test_run_config_fields() -> None:
    """TestRunConfig round-trips all required fields."""
    cfg = TestRunConfig(
        env_name="ctf-test",
        workspace=Path("/tmp/workspace"),
        timeout_seconds=300,
        inference_host="127.0.0.1",
        inference_port=8080,
        http_port=9090,
        tmp_secret_path=Path("/tmp/secret"),
    )
    assert cfg.env_name == "ctf-test"
    assert cfg.workspace == Path("/tmp/workspace")
    assert cfg.timeout_seconds == 300
    assert cfg.inference_host == "127.0.0.1"
    assert cfg.inference_port == 8080
    assert cfg.http_port == 9090
    assert cfg.tmp_secret_path == Path("/tmp/secret")


def test_test_run_outcome_transitions() -> None:
    """TestRun.outcome starts as None and accepts all valid literal values."""
    cfg = TestRunConfig(
        env_name="ctf-test",
        workspace=Path("/tmp/workspace"),
        timeout_seconds=300,
        inference_host="127.0.0.1",
        inference_port=8080,
        http_port=9090,
        tmp_secret_path=Path("/tmp/secret"),
    )
    fs_secret = Secret(name="filesystem", value="aaa")
    net_secret = Secret(name="network", value="bbb")
    run = TestRun(
        config=cfg,
        filesystem_secret=fs_secret,
        network_secret=net_secret,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert run.outcome is None

    run.outcome = "pass"
    assert run.outcome == "pass"

    run.outcome = "fail"
    assert run.outcome == "fail"

    run.outcome = "error"
    assert run.outcome == "error"

    run.outcome = "inconclusive"
    assert run.outcome == "inconclusive"
