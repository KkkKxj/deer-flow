#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any


DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
SECOPS_BIZ_SERVICE_URL_ENV = "SECOPS_BIZ_SERVICE_URL"
SECOPS_MOCK_BACKEND_URL_ENV = "SECOPS_MOCK_BACKEND_URL"

DEFAULT_SECOPS_BIZ_SERVICE_URL = "http://localhost:8080"
DEFAULT_SECOPS_MOCK_BACKEND_URL = "http://localhost:8082"
DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL = "http://host.docker.internal:18083"
DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL = "http://host.docker.internal:18082"


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _biz_base_url() -> str:
    configured = os.getenv(SECOPS_BIZ_SERVICE_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL
    return DEFAULT_SECOPS_BIZ_SERVICE_URL


def _mock_base_url() -> str:
    configured = os.getenv(SECOPS_MOCK_BACKEND_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL
    return DEFAULT_SECOPS_MOCK_BACKEND_URL


def _request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers=request_headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _continuation_payload(
    *,
    alert_id: str,
    thread_id: str,
    alert_type: str,
    agent_name: str,
) -> dict[str, Any]:
    return {
        "continuation": {
            "threadId": thread_id,
            "agentName": agent_name,
            "alertId": str(alert_id),
            "alertType": alert_type,
            "uiApp": "dashboard-workspace",
            "continuationDispatchedAt": None,
            "continuationRunId": None,
        }
    }


def create_ticket(
    *,
    alert_id: str,
    thread_id: str,
    alert_type: str,
    agent_name: str,
    title: str | None = None,
) -> dict[str, Any]:
    try:
        continuation_payload = _continuation_payload(
            alert_id=alert_id,
            thread_id=thread_id,
            alert_type=alert_type,
            agent_name=agent_name,
        )
        ticket_title = title or f"{alert_type} #{alert_id}"
        external_payload = json.dumps(continuation_payload, separators=(",", ":"))

        bootstrap_body = _request_json(
            _biz_base_url(),
            "POST",
            "/api/biz/remediation/executions/bootstrap",
            payload={
                "alertId": str(alert_id),
                "actionType": alert_type,
                "operator": agent_name,
                "initialMessage": "Preparing external ticket handoff",
                "externalPayload": external_payload,
            },
        )
        ticket_body = _request_json(
            _mock_base_url(),
            "POST",
            "/api/mock/tickets",
            payload={
                "jobId": bootstrap_body["jobId"],
                "alertId": str(alert_id),
                "title": ticket_title,
                "trackingMode": "callback",
                "operator": agent_name,
                "externalPayload": external_payload,
            },
        )
        return {
            "ok": True,
            "alertId": str(alert_id),
            "threadId": thread_id,
            "jobId": str(bootstrap_body["jobId"]),
            "executionId": str(bootstrap_body["executionId"]),
            "ticketId": str(ticket_body["ticketId"]),
            "externalTaskId": str(ticket_body["externalTaskId"]),
            "status": str(ticket_body["status"]),
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "alertId": str(alert_id), "threadId": thread_id, "error": str(error)}


def get_external_status(external_task_id: str) -> dict[str, Any]:
    try:
        body = _request_json(_mock_base_url(), "GET", f"/api/mock/tickets/external-status/{external_task_id}")
        return {
            "ok": True,
            "externalTaskId": external_task_id,
            "status": body.get("status"),
            "message": body.get("message"),
            "payload": body.get("payload"),
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "externalTaskId": external_task_id, "error": str(error)}


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock ticket skill-local operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--alert-id", required=True)
    create_parser.add_argument("--thread-id", required=True)
    create_parser.add_argument("--alert-type", required=True)
    create_parser.add_argument("--agent-name", default="secops-agent")
    create_parser.add_argument("--title")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--external-task-id", required=True)

    args = parser.parse_args(argv)
    if args.command == "create":
        _print_json(
            create_ticket(
                alert_id=args.alert_id,
                thread_id=args.thread_id,
                alert_type=args.alert_type,
                agent_name=args.agent_name,
                title=args.title,
            )
        )
    elif args.command == "status":
        _print_json(get_external_status(args.external_task_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
