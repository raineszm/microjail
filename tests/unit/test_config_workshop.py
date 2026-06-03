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


def test_system_sdk_present_when_inference_set() -> None:
    """System SDK is present when inference is configured."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    sdk_names = [s["name"] for s in doc.get("sdks", [])]
    assert "system" in sdk_names


def test_tunnel_keys_present_when_inference_set() -> None:
    """Tunnel, plugs, and slots keys appear when inference is configured."""
    yaml_str = generate_workshop_yaml(_full_config())
    for required in ("tunnel", "plugs", "slots"):
        assert required in yaml_str, (
            f"Required key '{required}' missing in workshop.yaml"
        )


def test_no_system_sdk_when_inference_not_set() -> None:
    """System SDK is absent when inference is not configured."""
    doc = _parse(generate_workshop_yaml(_bare_config()))
    sdk_names = [s["name"] for s in doc.get("sdks", [])]
    assert "system" not in sdk_names


def test_no_tunnel_keys_when_inference_not_set() -> None:
    """No tunnel, plugs, or slots keys when inference is not configured."""
    yaml_str = generate_workshop_yaml(_bare_config())
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


def test_inference_sdk_endpoint() -> None:
    """System SDK slot has endpoint localhost:8080."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    system_sdk = next(s for s in doc["sdks"] if s["name"] == "system")
    assert system_sdk["slots"]["llama-cpp"]["endpoint"] == "localhost:8080"


def test_inference_sdk_plugs() -> None:
    """Project SDK has plugs with tunnel interface."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    llama_sdk = next(s for s in doc["sdks"] if s["name"] == "llama-cpp")
    assert llama_sdk["plugs"]["llama-cpp"]["interface"] == "tunnel"


def test_inference_sdk_slots() -> None:
    """System SDK has slots with tunnel interface."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    system_sdk = next(s for s in doc["sdks"] if s["name"] == "system")
    assert system_sdk["slots"]["llama-cpp"]["interface"] == "tunnel"


def test_sdk_ordering() -> None:
    """SDKs appear in order: opencode, skills, inference, system."""
    doc = _parse(generate_workshop_yaml(_full_config()))
    sdk_names = [s["name"] for s in doc["sdks"]]
    assert sdk_names == ["opencode", "skills", "llama-cpp", "system"]


def test_inference_sdk_absent_when_no_inference() -> None:
    """Project inference SDK is absent when inference is not configured."""
    doc = _parse(generate_workshop_yaml(_bare_config()))
    sdk_names = [s["name"] for s in doc.get("sdks", [])]
    assert "llama-cpp" not in sdk_names
