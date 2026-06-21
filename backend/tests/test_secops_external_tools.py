import asyncio
import json
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


def test_get_alert_workspace_context_exposes_parsed_alert_detail(monkeypatch):
    base_url = "http://biz-service.local"
    alert_id = "1019"
    alert_url = f"{base_url}/api/biz/alerts/{alert_id}"
    detail = {
        "fieldValues": {
            "judgment_result": "222",
            "kill_chain": "exploitation",
        }
    }
    payload = {
        "id": alert_id,
        "type": "sdwhby-alert",
        "status": "pending",
        "detail": json.dumps(detail),
    }
    fake_client = _FakeClient({("GET", alert_url): _FakeResponse(payload, method="GET", url=alert_url)})

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.get_alert_workspace_context_tool, runtime=_runtime(alert_id=alert_id), alert_id=None)

    assert result["ok"] is True
    assert result["alert"] == payload
    assert result["alertDetail"] == detail
    assert fake_client.gets == [(alert_url, None)]


def test_get_alert_workspace_context_uses_raw_payload_when_detail_is_absent(monkeypatch):
    base_url = "http://biz-service.local"
    alert_id = "1020"
    alert_url = f"{base_url}/api/biz/alerts/{alert_id}"
    raw_payload = {
        "data": {
            "fieldValues": {
                "source_ip": "10.169.64.120",
                "target_ip": "10.168.12.234",
            }
        }
    }
    payload = {
        "id": alert_id,
        "type": "sdwhby-alert",
        "status": "pending",
        "rawPayload": json.dumps(raw_payload),
    }
    fake_client = _FakeClient({("GET", alert_url): _FakeResponse(payload, method="GET", url=alert_url)})

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.get_alert_workspace_context_tool, runtime=_runtime(alert_id=alert_id), alert_id=None)

    assert result["ok"] is True
    assert result["alert"] == payload
    assert result["alertDetail"] == raw_payload
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
    assert result["threadId"] == thread_id
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
                {"id": "1019", "status": "processing"},
                method="PATCH",
                url=status_url,
            ),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(secops_tools.update_alert_status_tool, runtime=_runtime(thread_id=thread_id), status="processing")

    assert result["ok"] is True
    assert result["alertId"] == "1019"
    assert fake_client.gets == [(binding_url, None)]
    assert fake_client.patches == [(status_url, {"status": "processing"}, None)]


def test_complete_alert_with_report_posts_report_backed_completion(monkeypatch):
    base_url = "http://biz-service.local"
    complete_url = f"{base_url}/api/biz/alerts/1019/complete-with-report"
    payload = {
        "alert": {
            "id": "1019",
            "status": "processed",
            "reportUrl": "http://biz-service.local/api/biz/public/alert-reports/1019",
        },
        "report": {"id": "report-1019", "alertId": "1019", "finalStatus": "processed"},
    }
    fake_client = _FakeClient({("POST", complete_url): _FakeResponse(payload, method="POST", url=complete_url)})

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(
        secops_tools.complete_alert_with_report_tool,
        runtime=_runtime(alert_id="1019"),
        status="processed",
        title="Alert handled",
        summary="The alert was handled.",
        content_markdown="# Alert handled",
    )

    assert result["ok"] is True
    assert result["alertId"] == "1019"
    assert result["status"] == "processed"
    assert result["reportUrl"] == "http://biz-service.local/api/biz/public/alert-reports/1019"
    assert fake_client.posts == [
        (
            complete_url,
            {
                "status": "processed",
                "title": "Alert handled",
                "summary": "The alert was handled.",
                "contentMarkdown": "# Alert handled",
                "agentName": "secops-agent",
                "threadId": None,
                "runId": None,
            },
            None,
        )
    ]


def test_complete_alert_with_report_resolves_alert_id_from_thread_binding(monkeypatch):
    base_url = "http://biz-service.local"
    thread_id = "thread-1"
    binding_url = f"{base_url}/api/biz/alerts/workspace-threads/{thread_id}"
    complete_url = f"{base_url}/api/biz/alerts/1019/complete-with-report"
    fake_client = _FakeClient(
        {
            ("GET", binding_url): _FakeResponse(
                {"alertId": "1019", "threadId": thread_id},
                method="GET",
                url=binding_url,
            ),
            ("POST", complete_url): _FakeResponse(
                {
                    "alert": {
                        "id": "1019",
                        "status": "failed",
                        "reportUrl": "http://biz-service.local/api/biz/public/alert-reports/1019",
                    },
                    "report": {"id": "report-1019", "alertId": "1019", "finalStatus": "failed"},
                },
                method="POST",
                url=complete_url,
            ),
        }
    )

    monkeypatch.setattr(secops_tools, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(secops_tools.httpx, "Client", lambda timeout: fake_client)

    result = _run(
        secops_tools.complete_alert_with_report_tool,
        runtime=_runtime(thread_id=thread_id),
        status="failed",
        title="Alert failed",
        summary="The alert could not be verified.",
        content_markdown="# Alert failed",
    )

    assert result["ok"] is True
    assert result["alertId"] == "1019"
    assert result["status"] == "failed"
    assert fake_client.gets == [(binding_url, None)]
    assert fake_client.posts[0][0] == complete_url


def test_secops_native_tools_are_core_alert_lifecycle_only():
    assert hasattr(secops_tools, "get_alert_workspace_context_tool")
    assert hasattr(secops_tools, "update_alert_status_tool")
    assert hasattr(secops_tools, "complete_alert_with_report_tool")

    forbidden_mock_tool_names = tuple(
        "_".join(parts)
        for parts in (
            ("get", "mock", "auth", "user", "context"),
            ("kick", "mock", "auth", "user", "sessions"),
            ("disable", "mock", "auth", "user"),
            ("create", "mock", "ticket", "tool"),
            ("get", "mock", "ticket", "external", "status", "tool"),
        )
    )

    for tool_name in forbidden_mock_tool_names:
        assert not hasattr(secops_tools, tool_name), tool_name
