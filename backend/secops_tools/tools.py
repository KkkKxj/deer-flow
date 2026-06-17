"""SecOps custom tools backed by SecOpsCopilot services.

These tools intentionally live outside ``deerflow`` so V2 can add SecOps
business capabilities without modifying DeerFlow harness source code.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from langchain.tools import ToolRuntime, tool

DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0

SECOPS_BIZ_SERVICE_URL_ENV = "SECOPS_BIZ_SERVICE_URL"

DEFAULT_SECOPS_BIZ_SERVICE_URL = "http://localhost:8080"
DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL = "http://host.docker.internal:18083"
ALLOWED_ALERT_STATUSES = {"processing"}
ALLOWED_TERMINAL_ALERT_STATUSES = {"processed", "failed"}


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_biz_service_base_url() -> str:
    configured = os.getenv(SECOPS_BIZ_SERVICE_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL
    return DEFAULT_SECOPS_BIZ_SERVICE_URL


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
        raise ValueError("status must be processing; use complete_alert_with_report for processed or failed")

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


def complete_alert_with_report(
    alert_id: str,
    status: str,
    title: str,
    summary: str,
    content_markdown: str,
    *,
    agent_name: str | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    normalized_status = status.strip().lower()
    if normalized_status not in ALLOWED_TERMINAL_ALERT_STATUSES:
        raise ValueError("status must be one of processed, failed")
    if not title or title.strip() == "":
        raise ValueError("title is required")
    if not summary or summary.strip() == "":
        raise ValueError("summary is required")
    if not content_markdown or content_markdown.strip() == "":
        raise ValueError("content_markdown is required")

    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    complete_url = f"{resolved_base_url}/api/biz/alerts/{alert_id}/complete-with-report"
    payload = {
        "status": normalized_status,
        "title": title.strip(),
        "summary": summary.strip(),
        "contentMarkdown": content_markdown.strip(),
        "agentName": agent_name,
        "threadId": thread_id,
        "runId": run_id,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(complete_url, json=payload)
        response.raise_for_status()
        body = response.json()

    alert = body.get("alert") if isinstance(body.get("alert"), dict) else {}
    report = body.get("report") if isinstance(body.get("report"), dict) else {}
    report_url = alert.get("reportUrl") or body.get("reportUrl")
    final_status = alert.get("status") or report.get("finalStatus") or normalized_status

    return {
        "ok": True,
        "alertId": str(alert_id),
        "status": final_status,
        "reportUrl": report_url,
        "alert": alert,
        "report": report,
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
        result = fetch_alert_workspace_context(resolved_alert_id)
        thread_id = _resolve_thread_id(runtime)
        if thread_id:
            result["threadId"] = thread_id
        return result
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
    """Mark the current alert as processing in SecOps biz-service.

    Args:
        status: Must be processing. Use complete_alert_with_report for processed or failed.
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


@tool("complete_alert_with_report", parse_docstring=True)
def complete_alert_with_report_tool(
    runtime: ToolRuntime,
    status: str,
    title: str,
    summary: str,
    content_markdown: str,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Complete the current alert by saving an agent-generated report first.

    Args:
        status: Final alert status, either processed or failed.
        title: Report title.
        summary: Short report summary.
        content_markdown: Full Markdown report body generated by the agent.
        alert_id: Optional alert ID. If omitted, the active thread alert ID is used.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run this tool inside an alert-bound thread.",
        }

    try:
        return complete_alert_with_report(
            resolved_alert_id,
            status,
            title,
            summary,
            content_markdown,
            agent_name=_resolve_runtime_value(runtime, "agent_name"),
            thread_id=_resolve_thread_id(runtime),
            run_id=_resolve_runtime_value(runtime, "run_id"),
        )
    except ValueError as error:
        return {"ok": False, "alertId": str(resolved_alert_id), "error": str(error)}
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": _format_http_error("Failed to complete alert with report", error, "biz-service"),
        }
