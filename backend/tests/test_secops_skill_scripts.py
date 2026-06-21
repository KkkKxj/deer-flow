import importlib.util
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEERFLOW_ROOT = BACKEND_ROOT.parent
SECOPS_SKILL_ROOT = DEERFLOW_ROOT / "skills" / "custom"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mock_auth_script_context_returns_user_and_sessions(monkeypatch):
    script = _load_module(
        SECOPS_SKILL_ROOT / "mock-illegal-login-responder" / "scripts" / "mock_auth.py",
        "mock_auth_script",
    )
    calls = []

    def fake_request(method, path, *, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if path == "/api/mock/auth/login":
            return {"token": "mock-token"}
        if path == "/api/mock/auth/users":
            return {"users": [{"username": "test", "disabled": False, "commonIp": "172.16.8.1"}]}
        if path == "/api/mock/auth/sessions":
            return {"sessions": [{"sessionId": "session-1", "username": "test"}]}
        raise AssertionError(path)

    monkeypatch.setattr(script, "_request_json", fake_request)

    result = script.get_context("test")

    assert result["ok"] is True
    assert result["commonIp"] == "172.16.8.1"
    assert result["sessions"] == [{"sessionId": "session-1", "username": "test"}]
    assert calls[0] == ("POST", "/api/mock/auth/login", {"username": "admin", "password": "111111"}, None)
    assert calls[1][3] == {"X-Mock-Auth-Token": "mock-token"}


def test_mock_auth_script_kick_only_matching_sessions(monkeypatch):
    script = _load_module(
        SECOPS_SKILL_ROOT / "mock-illegal-login-responder" / "scripts" / "mock_auth.py",
        "mock_auth_script_kick",
    )
    calls = []

    def fake_request(method, path, *, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if path == "/api/mock/auth/login":
            return {"token": "mock-token"}
        if path == "/api/mock/auth/sessions":
            return {
                "sessions": [
                    {"sessionId": "session-1", "username": "test"},
                    {"sessionId": "session-2", "username": "test"},
                    {"sessionId": "session-9", "username": "admin"},
                ]
            }
        if path in {"/api/mock/auth/sessions/session-1/kick", "/api/mock/auth/sessions/session-2/kick"}:
            return {"ok": True}
        raise AssertionError(path)

    monkeypatch.setattr(script, "_request_json", fake_request)

    result = script.kick_sessions("test")

    assert result["ok"] is True
    assert result["kickedSessionIds"] == ["session-1", "session-2"]
    assert ("POST", "/api/mock/auth/sessions/session-9/kick", None, {"X-Mock-Auth-Token": "mock-token"}) not in calls


def test_mock_auth_script_disable_user(monkeypatch):
    script = _load_module(
        SECOPS_SKILL_ROOT / "mock-illegal-login-responder" / "scripts" / "mock_auth.py",
        "mock_auth_script_disable",
    )

    def fake_request(method, path, *, payload=None, headers=None):
        if path == "/api/mock/auth/login":
            return {"token": "mock-token"}
        if path == "/api/mock/auth/users/test/disable":
            return {"username": "test", "disabled": True}
        raise AssertionError(path)

    monkeypatch.setattr(script, "_request_json", fake_request)

    result = script.disable_user("test")

    assert result["ok"] is True
    assert result["disabled"] is True


def test_mock_ticket_script_create_builds_continuation_payload(monkeypatch):
    script = _load_module(
        SECOPS_SKILL_ROOT / "mock-external-ticket-responder" / "scripts" / "mock_ticket.py",
        "mock_ticket_script",
    )
    calls = []

    def fake_request(base_url, method, path, *, payload=None, headers=None):
        calls.append((base_url, method, path, payload, headers))
        if path == "/api/biz/remediation/executions/bootstrap":
            return {"executionId": "exec-1", "jobId": "job-1", "result": "running"}
        if path == "/api/mock/tickets":
            return {"ticketId": "MT-1", "executionId": "exec-1", "externalTaskId": "ext-1", "status": "processing"}
        raise AssertionError(path)

    monkeypatch.setattr(script, "_request_json", fake_request)
    monkeypatch.setattr(script, "_biz_base_url", lambda: "http://biz.local")
    monkeypatch.setattr(script, "_mock_base_url", lambda: "http://mock.local")

    result = script.create_ticket(
        alert_id="1020",
        thread_id="thread-1",
        alert_type="mock-external-ticket-remediation",
        agent_name="secops-agent",
        title="External remediation ticket",
    )

    assert result["ok"] is True
    assert result["jobId"] == "job-1"
    assert result["ticketId"] == "MT-1"
    assert calls[0][0] == "http://biz.local"
    assert calls[0][3]["alertId"] == "1020"
    assert "thread-1" in calls[0][3]["externalPayload"]
    assert calls[1][0] == "http://mock.local"
    assert calls[1][3]["trackingMode"] == "callback"


def test_mock_ticket_script_status_reads_external_status(monkeypatch):
    script = _load_module(
        SECOPS_SKILL_ROOT / "mock-external-ticket-responder" / "scripts" / "mock_ticket.py",
        "mock_ticket_script_status",
    )

    def fake_request(base_url, method, path, *, payload=None, headers=None):
        assert base_url == "http://mock.local"
        assert method == "GET"
        assert path == "/api/mock/tickets/external-status/ext-1"
        return {"status": "success", "message": "done", "payload": {"ticketId": "MT-1"}}

    monkeypatch.setattr(script, "_request_json", fake_request)
    monkeypatch.setattr(script, "_mock_base_url", lambda: "http://mock.local")

    result = script.get_external_status("ext-1")

    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["payload"]["ticketId"] == "MT-1"
