"""SecOps custom tools backed by SecOpsCopilot services.

These tools intentionally live outside ``deerflow`` so V2 can add SecOps
business capabilities without modifying DeerFlow harness source code.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from langchain.tools import ToolRuntime, tool

DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0

SECOPS_BIZ_SERVICE_URL_ENV = "SECOPS_BIZ_SERVICE_URL"
SECOPS_MOCK_BACKEND_URL_ENV = "SECOPS_MOCK_BACKEND_URL"
SECOPS_MOCK_AUTH_USERNAME_ENV = "SECOPS_MOCK_AUTH_USERNAME"
SECOPS_MOCK_AUTH_PASSWORD_ENV = "SECOPS_MOCK_AUTH_PASSWORD"

DEFAULT_SECOPS_BIZ_SERVICE_URL = "http://localhost:8080"
DEFAULT_SECOPS_MOCK_BACKEND_URL = "http://localhost:8082"
DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL = "http://host.docker.internal:18083"
DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL = "http://host.docker.internal:18082"
DEFAULT_SECOPS_MOCK_AUTH_USERNAME = "admin"
DEFAULT_SECOPS_MOCK_AUTH_PASSWORD = "111111"
AUTH_HEADER = "X-Mock-Auth-Token"
ALLOWED_ALERT_STATUSES = {"processing", "processed", "failed"}


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_biz_service_base_url() -> str:
    configured = os.getenv(SECOPS_BIZ_SERVICE_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL
    return DEFAULT_SECOPS_BIZ_SERVICE_URL


def _resolve_mock_backend_base_url() -> str:
    configured = os.getenv(SECOPS_MOCK_BACKEND_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL
    return DEFAULT_SECOPS_MOCK_BACKEND_URL


def _resolve_operator_credentials() -> tuple[str, str]:
    return (
        os.getenv(SECOPS_MOCK_AUTH_USERNAME_ENV, DEFAULT_SECOPS_MOCK_AUTH_USERNAME),
        os.getenv(SECOPS_MOCK_AUTH_PASSWORD_ENV, DEFAULT_SECOPS_MOCK_AUTH_PASSWORD),
    )


def _resolve_runtime_value(runtime: Any, key: str) -> str | None:
    context = getattr(runtime, "context", None)
    if isinstance(context, dict) and context.get(key):
        return str(context[key])

    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    if configurable.get(key):
        return str(configurable[key])

    return None


def _resolve_alert_id_from_thread_binding(
    thread_id: str,
    *,
    base_url: str | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> str | None:
    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    binding_url = f"{resolved_base_url}/api/biz/alerts/workspace-threads/{thread_id}"

    with httpx.Client(timeout=timeout) as client:
        response = client.get(binding_url)
        response.raise_for_status()
        body = response.json()

    resolved_alert_id = body.get("alertId")
    if resolved_alert_id is None and isinstance(body.get("alert"), dict):
        resolved_alert_id = body["alert"].get("id")
    if resolved_alert_id is None or str(resolved_alert_id).strip() == "":
        raise ValueError(f"workspace thread {thread_id} is not bound to an alert")
    return str(resolved_alert_id)


def _resolve_alert_id(runtime: Any, alert_id: str | None) -> str | None:
    explicit_alert_id = alert_id or _resolve_runtime_value(runtime, "alert_id")
    if explicit_alert_id:
        return str(explicit_alert_id)

    thread_id = _resolve_thread_id(runtime)
    if not thread_id:
        return None

    try:
        return _resolve_alert_id_from_thread_binding(thread_id)
    except Exception:  # noqa: BLE001
        return None


def _resolve_thread_id(runtime: Any) -> str | None:
    return _resolve_runtime_value(runtime, "thread_id")


def _resolve_agent_name(runtime: Any) -> str:
    return _resolve_runtime_value(runtime, "agent_name") or "secops-agent"


def _resolve_alert_type(runtime: Any) -> str:
    return _resolve_runtime_value(runtime, "alert_type") or "mock-external-ticket-remediation"


def _login(client: httpx.Client, base_url: str) -> str:
    username, password = _resolve_operator_credentials()
    response = client.post(
        f"{base_url}/api/mock/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    token = response.json().get("token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("mock auth login did not return a token")
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {AUTH_HEADER: token}


def _format_http_error(prefix: str, error: Exception, service: str) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        return f"{prefix}: {service} returned HTTP {response.status_code} for {response.request.url}"
    return f"{prefix}: {error}"


def fetch_alert_workspace_context(
    alert_id: str,
    *,
    base_url: str | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    alert_url = f"{resolved_base_url}/api/biz/alerts/{alert_id}"

    with httpx.Client(timeout=timeout) as client:
        response = client.get(alert_url)
        response.raise_for_status()
        alert = response.json()

    return {"ok": True, "alertId": str(alert_id), "alert": alert}


def patch_alert_status(
    alert_id: str,
    status: str,
    *,
    base_url: str | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    normalized_status = status.strip().lower()
    if normalized_status not in ALLOWED_ALERT_STATUSES:
        raise ValueError("status must be one of processing, processed, failed")

    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    status_url = f"{resolved_base_url}/api/biz/alerts/{alert_id}/status"

    with httpx.Client(timeout=timeout) as client:
        response = client.patch(status_url, json={"status": normalized_status})
        response.raise_for_status()
        alert = response.json()

    return {
        "ok": True,
        "alertId": str(alert_id),
        "status": normalized_status,
        "alert": alert,
    }


@tool("get_alert_workspace_context", parse_docstring=True)
def get_alert_workspace_context_tool(
    runtime: ToolRuntime,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Load the authoritative alert workspace context from SecOps biz-service.

    Args:
        alert_id: Optional alert ID. If omitted, the active thread alert ID is used.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run this tool inside an alert-bound thread.",
        }

    try:
        return fetch_alert_workspace_context(resolved_alert_id)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": _format_http_error("Failed to load alert workspace context", error, "biz-service"),
        }


@tool("update_alert_status", parse_docstring=True)
def update_alert_status_tool(
    runtime: ToolRuntime,
    status: str,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Update the current alert status in SecOps biz-service.

    Args:
        status: One of processing, processed, failed.
        alert_id: Optional alert ID. If omitted, the active thread alert ID is used.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run this tool inside an alert-bound thread.",
        }

    try:
        return patch_alert_status(resolved_alert_id, status)
    except ValueError as error:
        return {"ok": False, "alertId": str(resolved_alert_id), "error": str(error)}
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": _format_http_error("Failed to update alert status", error, "biz-service"),
        }


@tool("get_mock_auth_user_context", parse_docstring=True)
def get_mock_auth_user_context(username: str) -> dict[str, Any]:
    """Load the current mock-auth state for one username.

    Args:
        username: Target username in the mock auth system.
    """
    base_url = _resolve_mock_backend_base_url()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            token = _login(client, base_url)
            users = client.get(f"{base_url}/api/mock/auth/users", headers=_auth_headers(token))
            users.raise_for_status()
            sessions = client.get(f"{base_url}/api/mock/auth/sessions", headers=_auth_headers(token))
            sessions.raise_for_status()

        user = next((item for item in users.json().get("users", []) if item.get("username") == username), None)
        active_sessions = [item for item in sessions.json().get("sessions", []) if item.get("username") == username]
        return {
            "ok": True,
            "username": username,
            "userExists": user is not None,
            "disabled": bool(user.get("disabled")) if user else False,
            "commonIp": str(user.get("commonIp") or "") if user else "",
            "sessions": active_sessions,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "username": username,
            "error": _format_http_error("Failed to load mock auth user context", error, "mock backend"),
        }


@tool("kick_mock_auth_user_sessions", parse_docstring=True)
def kick_mock_auth_user_sessions(username: str) -> dict[str, Any]:
    """Kick every active mock-auth session for one username.

    Args:
        username: Target username in the mock auth system.
    """
    base_url = _resolve_mock_backend_base_url()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            token = _login(client, base_url)
            sessions_response = client.get(f"{base_url}/api/mock/auth/sessions", headers=_auth_headers(token))
            sessions_response.raise_for_status()
            matching_sessions = [
                item for item in sessions_response.json().get("sessions", [])
                if item.get("username") == username
            ]

            kicked_ids: list[str] = []
            for session in matching_sessions:
                session_id = str(session["sessionId"])
                kick_response = client.post(
                    f"{base_url}/api/mock/auth/sessions/{session_id}/kick",
                    headers=_auth_headers(token),
                )
                kick_response.raise_for_status()
                kicked_ids.append(session_id)

        return {
            "ok": True,
            "username": username,
            "kickedSessionCount": len(kicked_ids),
            "kickedSessionIds": kicked_ids,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "username": username,
            "error": _format_http_error("Failed to kick mock auth user sessions", error, "mock backend"),
        }


@tool("disable_mock_auth_user", parse_docstring=True)
def disable_mock_auth_user(username: str) -> dict[str, Any]:
    """Disable one mock-auth user after session containment.

    Args:
        username: Target username in the mock auth system.
    """
    base_url = _resolve_mock_backend_base_url()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            token = _login(client, base_url)
            response = client.post(
                f"{base_url}/api/mock/auth/users/{username}/disable",
                headers=_auth_headers(token),
            )
            response.raise_for_status()
            user = response.json()

        return {
            "ok": True,
            "username": username,
            "disabled": bool(user.get("disabled")),
            "user": user,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "username": username,
            "error": _format_http_error("Failed to disable mock auth user", error, "mock backend"),
        }


@tool("create_mock_ticket", parse_docstring=True)
def create_mock_ticket_tool(
    runtime: ToolRuntime,
    title: str | None = None,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Create one callback-tracked mock ticket for the active alert thread.

    Args:
        title: Optional ticket title. If omitted, a title is derived from the alert.
        alert_id: Optional alert ID. If omitted, the active thread alert ID is used.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    resolved_thread_id = _resolve_thread_id(runtime)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run inside an alert-bound thread.",
        }
    if resolved_thread_id is None:
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": "Missing thread_id. Callback continuation requires the original alert thread id.",
        }

    agent_name = _resolve_agent_name(runtime)
    alert_type = _resolve_alert_type(runtime)
    continuation_payload = {
        "continuation": {
            "threadId": resolved_thread_id,
            "agentName": agent_name,
            "alertId": str(resolved_alert_id),
            "alertType": alert_type,
            "uiApp": "dashboard-workspace",
            "continuationDispatchedAt": None,
            "continuationRunId": None,
        }
    }

    bootstrap_url = f"{_resolve_biz_service_base_url()}/api/biz/remediation/executions/bootstrap"
    ticket_url = f"{_resolve_mock_backend_base_url()}/api/mock/tickets"
    ticket_title = title or f"{alert_type} #{resolved_alert_id}"

    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            bootstrap_response = client.post(
                bootstrap_url,
                json={
                    "alertId": str(resolved_alert_id),
                    "actionType": alert_type,
                    "operator": agent_name,
                    "initialMessage": "Preparing external ticket handoff",
                    "externalPayload": json.dumps(continuation_payload),
                },
            )
            bootstrap_response.raise_for_status()
            bootstrap_body = bootstrap_response.json()

            ticket_response = client.post(
                ticket_url,
                json={
                    "jobId": bootstrap_body["jobId"],
                    "alertId": str(resolved_alert_id),
                    "title": ticket_title,
                    "trackingMode": "callback",
                    "operator": agent_name,
                    "externalPayload": json.dumps(continuation_payload),
                },
            )
            ticket_response.raise_for_status()
            ticket_body = ticket_response.json()
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": _format_http_error("Failed to create mock ticket", error, "SecOps service"),
        }

    return {
        "ok": True,
        "alertId": str(resolved_alert_id),
        "threadId": resolved_thread_id,
        "jobId": str(bootstrap_body["jobId"]),
        "executionId": str(bootstrap_body["executionId"]),
        "ticketId": str(ticket_body["ticketId"]),
        "externalTaskId": str(ticket_body["externalTaskId"]),
        "status": str(ticket_body["status"]),
    }


@tool("get_mock_ticket_external_status", parse_docstring=True)
def get_mock_ticket_external_status_tool(external_task_id: str) -> dict[str, Any]:
    """Load the current state for one mock external ticket.

    Args:
        external_task_id: The external task id returned by create_mock_ticket.
    """
    status_url = f"{_resolve_mock_backend_base_url()}/api/mock/tickets/external-status/{external_task_id}"
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = client.get(status_url)
            response.raise_for_status()
            body = response.json()
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "externalTaskId": external_task_id,
            "error": _format_http_error("Failed to load mock ticket external status", error, "mock backend"),
        }

    return {
        "ok": True,
        "externalTaskId": external_task_id,
        "status": body.get("status"),
        "message": body.get("message"),
        "payload": body.get("payload"),
    }
