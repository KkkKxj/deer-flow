import asyncio
from types import SimpleNamespace

import httpx

import secops_tools.tools as secops_tools


class _FakeResponse:
    def __init__(self, payload, *, method: str, url: str, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request(method, url)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.gets = []
        self.posts = []
        self.patches = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        self.gets.append((url, headers))
        return self._responses[("GET", url)]

    def post(self, url, json=None, headers=None):
        self.posts.append((url, json, headers))
        return self._responses[("POST", url)]

    def patch(self, url, json=None, headers=None):
        self.patches.append((url, json, headers))
        return self._responses[("PATCH", url)]


def _runtime(*, alert_id=None, alert_type=None, thread_id=None, agent_name="secops-agent"):
    context = {}
    configurable = {}
    if alert_id is not None:
        context["alert_id"] = alert_id
    if alert_type is not None:
        context["alert_type"] = alert_type
    if thread_id is not None:
        context["thread_id"] = thread_id
        configurable["thread_id"] = thread_id
    if agent_name is not None:
        context["agent_name"] = agent_name
        configurable["agent_name"] = agent_name
    return SimpleNamespace(context=context, config={"configurable": configurable})


def _run(tool, **kwargs):
    coroutine = getattr(tool, "coroutine", None)
    if coroutine is not None:
        return asyncio.run(coroutine(**kwargs))
    return tool.func(**kwargs)


def test_get_alert_workspace_context_uses_runtime_alert_id(monkeypatch):
    base_url = "http://biz-service.local"
    alert_id = "1019"
    alert_url = f"{base_url}/api/biz/alerts/{alert_id}"
    payload = {"id": alert_id, "type": "mock-user-illegal-login", "status": "pending"}
    fake_client = _FakeClient({("GET", alert_url): _FakeResponse(payload, method="GET", url=alert_url)})

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.get_alert_workspace_context_tool, runtime=_runtime(alert_id=alert_id), alert_id=None)

    assert result["ok"] is True
    assert result["alertId"] == alert_id
    assert result["alert"] == payload
    assert fake_client.gets == [(alert_url, None)]


def test_get_alert_workspace_context_resolves_alert_id_from_thread_binding(monkeypatch):
    base_url = "http://biz-service.local"
    thread_id = "thread-1"
    binding_url = f"{base_url}/api/biz/alerts/workspace-threads/{thread_id}"
    alert_url = f"{base_url}/api/biz/alerts/1019"
    payload = {"id": "1019", "type": "mock-user-illegal-login", "status": "pending"}
    fake_client = _FakeClient(
        {
            ("GET", binding_url): _FakeResponse(
                {"alertId": "1019", "threadId": thread_id},
                method="GET",
                url=binding_url,
            ),
            ("GET", alert_url): _FakeResponse(payload, method="GET", url=alert_url),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.get_alert_workspace_context_tool, runtime=_runtime(thread_id=thread_id), alert_id=None)

    assert result["ok"] is True
    assert result["alertId"] == "1019"
    assert result["alert"] == payload
    assert fake_client.gets == [(binding_url, None), (alert_url, None)]


def test_update_alert_status_patches_biz_service(monkeypatch):
    base_url = "http://biz-service.local"
    alert_url = f"{base_url}/api/biz/alerts/1019/status"
    payload = {"id": "1019", "status": "processing"}
    fake_client = _FakeClient({("PATCH", alert_url): _FakeResponse(payload, method="PATCH", url=alert_url)})

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.update_alert_status_tool, runtime=_runtime(alert_id="1019"), status="processing")

    assert result["ok"] is True
    assert result["status"] == "processing"
    assert fake_client.patches == [(alert_url, {"status": "processing"}, None)]


def test_update_alert_status_resolves_alert_id_from_thread_binding(monkeypatch):
    base_url = "http://biz-service.local"
    thread_id = "thread-1"
    binding_url = f"{base_url}/api/biz/alerts/workspace-threads/{thread_id}"
    status_url = f"{base_url}/api/biz/alerts/1019/status"
    fake_client = _FakeClient(
        {
            ("GET", binding_url): _FakeResponse(
                {"alertId": "1019", "threadId": thread_id},
                method="GET",
                url=binding_url,
            ),
            ("PATCH", status_url): _FakeResponse(
                {"id": "1019", "status": "processed"},
                method="PATCH",
                url=status_url,
            ),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.update_alert_status_tool, runtime=_runtime(thread_id=thread_id), status="processed")

    assert result["ok"] is True
    assert result["alertId"] == "1019"
    assert fake_client.gets == [(binding_url, None)]
    assert fake_client.patches == [(status_url, {"status": "processed"}, None)]


def test_get_mock_auth_user_context_returns_user_and_sessions(monkeypatch):
    base_url = "http://mock.local"
    login_url = f"{base_url}/api/mock/auth/login"
    users_url = f"{base_url}/api/mock/auth/users"
    sessions_url = f"{base_url}/api/mock/auth/sessions"
    fake_client = _FakeClient(
        {
            ("POST", login_url): _FakeResponse({"token": "mock-token"}, method="POST", url=login_url),
            ("GET", users_url): _FakeResponse(
                {"users": [{"username": "test", "disabled": False, "commonIp": "172.16.8.1"}]},
                method="GET",
                url=users_url,
            ),
            ("GET", sessions_url): _FakeResponse(
                {"sessions": [{"sessionId": "session-1", "username": "test"}]},
                method="GET",
                url=sessions_url,
            ),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_mock_backend_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.get_mock_auth_user_context, username="test")

    assert result["ok"] is True
    assert result["commonIp"] == "172.16.8.1"
    assert result["sessions"] == [{"sessionId": "session-1", "username": "test"}]


def test_kick_mock_auth_user_sessions_kicks_matching_sessions(monkeypatch):
    base_url = "http://mock.local"
    login_url = f"{base_url}/api/mock/auth/login"
    sessions_url = f"{base_url}/api/mock/auth/sessions"
    kick_one_url = f"{base_url}/api/mock/auth/sessions/session-1/kick"
    kick_two_url = f"{base_url}/api/mock/auth/sessions/session-2/kick"
    fake_client = _FakeClient(
        {
            ("POST", login_url): _FakeResponse({"token": "mock-token"}, method="POST", url=login_url),
            ("GET", sessions_url): _FakeResponse(
                {
                    "sessions": [
                        {"sessionId": "session-1", "username": "test"},
                        {"sessionId": "session-2", "username": "test"},
                        {"sessionId": "session-9", "username": "admin"},
                    ]
                },
                method="GET",
                url=sessions_url,
            ),
            ("POST", kick_one_url): _FakeResponse({"sessionId": "session-1"}, method="POST", url=kick_one_url),
            ("POST", kick_two_url): _FakeResponse({"sessionId": "session-2"}, method="POST", url=kick_two_url),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_mock_backend_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.kick_mock_auth_user_sessions, username="test")

    assert result["ok"] is True
    assert result["kickedSessionIds"] == ["session-1", "session-2"]


def test_disable_mock_auth_user_returns_disabled_state(monkeypatch):
    base_url = "http://mock.local"
    login_url = f"{base_url}/api/mock/auth/login"
    disable_url = f"{base_url}/api/mock/auth/users/test/disable"
    fake_client = _FakeClient(
        {
            ("POST", login_url): _FakeResponse({"token": "mock-token"}, method="POST", url=login_url),
            ("POST", disable_url): _FakeResponse({"username": "test", "disabled": True}, method="POST", url=disable_url),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_mock_backend_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.disable_mock_auth_user, username="test")

    assert result["ok"] is True
    assert result["disabled"] is True


def test_create_mock_ticket_bootstraps_execution_then_creates_callback_ticket(monkeypatch):
    biz_base = "http://biz-service.local"
    mock_base = "http://mock.local"
    bootstrap_url = f"{biz_base}/api/biz/remediation/executions/bootstrap"
    create_url = f"{mock_base}/api/mock/tickets"
    fake_client = _FakeClient(
        {
            ("POST", bootstrap_url): _FakeResponse(
                {"executionId": "exec-1", "jobId": "job-1", "result": "running"},
                method="POST",
                url=bootstrap_url,
            ),
            ("POST", create_url): _FakeResponse(
                {"ticketId": "MT-1", "executionId": "exec-1", "externalTaskId": "ext-1", "status": "processing"},
                method="POST",
                url=create_url,
            ),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: biz_base)
    monkeypatch.setattr(secops_tools, "_resolve_mock_backend_base_url", lambda: mock_base)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(
        secops_tools.create_mock_ticket_tool,
        runtime=_runtime(alert_id="1020", alert_type="mock-external-ticket-remediation", thread_id="thread-1"),
        title="External remediation ticket",
        alert_id=None,
    )

    assert result["ok"] is True
    assert result["jobId"] == "job-1"
    assert result["ticketId"] == "MT-1"
    assert fake_client.posts[0][1]["alertId"] == "1020"
    assert "thread-1" in fake_client.posts[0][1]["externalPayload"]
    assert fake_client.posts[1][1]["trackingMode"] == "callback"


def test_create_mock_ticket_resolves_alert_id_from_thread_binding(monkeypatch):
    biz_base = "http://biz-service.local"
    mock_base = "http://mock.local"
    thread_id = "thread-1"
    binding_url = f"{biz_base}/api/biz/alerts/workspace-threads/{thread_id}"
    bootstrap_url = f"{biz_base}/api/biz/remediation/executions/bootstrap"
    create_url = f"{mock_base}/api/mock/tickets"
    fake_client = _FakeClient(
        {
            ("GET", binding_url): _FakeResponse(
                {"alertId": "1020", "threadId": thread_id},
                method="GET",
                url=binding_url,
            ),
            ("POST", bootstrap_url): _FakeResponse(
                {"executionId": "exec-1", "jobId": "job-1", "result": "running"},
                method="POST",
                url=bootstrap_url,
            ),
            ("POST", create_url): _FakeResponse(
                {"ticketId": "MT-1", "executionId": "exec-1", "externalTaskId": "ext-1", "status": "processing"},
                method="POST",
                url=create_url,
            ),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: biz_base)
    monkeypatch.setattr(secops_tools, "_resolve_mock_backend_base_url", lambda: mock_base)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(
        secops_tools.create_mock_ticket_tool,
        runtime=_runtime(alert_type="mock-external-ticket-remediation", thread_id=thread_id),
        title="External remediation ticket",
        alert_id=None,
    )

    assert result["ok"] is True
    assert result["alertId"] == "1020"
    assert result["threadId"] == thread_id
    assert fake_client.gets == [(binding_url, None)]
    assert fake_client.posts[0][1]["alertId"] == "1020"


def test_get_mock_ticket_external_status_reads_mock_backend(monkeypatch):
    mock_base = "http://mock.local"
    status_url = f"{mock_base}/api/mock/tickets/external-status/ext-1"
    fake_client = _FakeClient(
        {
            ("GET", status_url): _FakeResponse(
                {"status": "success", "message": "done", "payload": {"ticketId": "MT-1"}},
                method="GET",
                url=status_url,
            )
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_mock_backend_base_url", lambda: mock_base)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.get_mock_ticket_external_status_tool, external_task_id="ext-1")

    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["payload"]["ticketId"] == "MT-1"
