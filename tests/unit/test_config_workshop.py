"""Unit tests for workshop.yaml generator."""

from ruamel.yaml import YAML

from microjail.config.models import EnvironmentConfig
from microjail.config.workshop import generate_workshop_yaml


def _parse(yaml_str: str) -> dict:  # type: ignore[type-arg]
    yaml = YAML()
    return yaml.load(yaml_str)


def _full_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        name="myproject",
        base_image="ubuntu@26.04",
        inference="llama-cpp",
        agent="opencode",
    )


def _bare_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        name="bareproject",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
    )


def test_name_set() -> None:
    """Environment name is written correctly."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    assert doc["name"] == "myproject"


def test_base_image_set() -> None:
    """Base image is written correctly."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    assert doc["base"] == "ubuntu@26.04"


def test_opencode_sdk_present() -> None:
    """Opencode SDK is present when agent == opencode."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    sdk_names = [s["name"] for s in doc["sdks"]]
    assert "opencode" in sdk_names


def test_skills_sdk_present() -> None:
    """Skills SDK is present when agent == opencode."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    sdk_names = [s["name"] for s in doc["sdks"]]
    assert "skills" in sdk_names


def test_no_system_sdk() -> None:
    """System SDK is never present (no TCP tunnel)."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    sdk_names = [s["name"] for s in doc.get("sdks", [])]
    assert "system" not in sdk_names


def test_no_tunnel_keys() -> None:
    """No tunnel, plugs, or slots keys appear anywhere in the output."""
    yaml_str = generate_workshop_yaml(_full_config())
    for forbidden in ("tunnel", "plugs", "slots"):
        assert forbidden not in yaml_str, (
            f"Forbidden key '{forbidden}' found in workshop.yaml"
        )


def test_opencode_sdk_channel() -> None:
    """Opencode SDK declares channel latest/stable."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    opencode_sdk = next(s for s in doc["sdks"] if s["name"] == "opencode")
    assert opencode_sdk["channel"] == "latest/stable"


def test_skills_sdk_channel() -> None:
    """Skills SDK declares channel latest/edge."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    skills_sdk = next(s for s in doc["sdks"] if s["name"] == "skills")
    assert skills_sdk["channel"] == "latest/edge"


def test_bare_init_empty_sdks() -> None:
    """Bare init (no flags) produces empty sdks list."""
    doc = _parse(generate_workshop_yaml(_bare_config()))
    assert doc.get("sdks") == [] or doc.get("sdks") is None


def test_output_is_valid_yaml() -> None:
    """Output is parseable YAML."""
    yaml_str = generate_workshop_yaml(_full_config())
    doc = _parse(yaml_str)
    assert isinstance(doc, dict)
