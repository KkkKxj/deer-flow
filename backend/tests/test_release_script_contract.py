from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "release.sh"


def test_release_script_wraps_native_deploy_for_v2_services() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "DEER_FLOW_REGISTRY_SERVICES:-frontend gateway" in text
    assert '"$REPO_ROOT/scripts/deploy.sh" build' in text
    assert '"$REPO_ROOT/scripts/deploy.sh" start' in text
    assert '"$REPO_ROOT/scripts/deploy.sh" down' in text


def test_release_script_does_not_keep_v1_runtime_modes() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "langgraph" not in text
    assert "--standard" not in text
    assert "--gateway" not in text


def test_release_script_supports_registry_lifecycle_commands() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    for command in ("release)", "build)", "push)", "pull)", "up)", "start)", "down)", "images)"):
        assert command in text
