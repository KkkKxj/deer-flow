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


def test_release_script_attaches_gateway_and_nginx_to_secops_network() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'connect_container_to_secops_network "deer-flow-nginx" "deer-flow-nginx"' in text
    assert 'connect_container_to_secops_network "deer-flow-gateway" "deer-flow-gateway"' in text
    assert "connect_runtime_to_secops_network" in text


def test_release_script_does_not_hide_runtime_inspect_failures() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '    docker container inspect "$container_name" >/dev/null\n' in text
    assert 'docker container inspect "$container_name" >/dev/null 2>&1' not in text
    assert 'if ! docker container inspect "$container_name"' not in text
    assert "is not present; skipped" not in text
    assert 'attached_networks="$(docker inspect "$container_name"' in text
