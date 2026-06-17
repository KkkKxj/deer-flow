#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any


DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
SECOPS_MOCK_BACKEND_URL_ENV = "SECOPS_MOCK_BACKEND_URL"
SECOPS_MOCK_AUTH_USERNAME_ENV = "SECOPS_MOCK_AUTH_USERNAME"
SECOPS_MOCK_AUTH_PASSWORD_ENV = "SECOPS_MOCK_AUTH_PASSWORD"

DEFAULT_SECOPS_MOCK_BACKEND_URL = "http://localhost:8082"
DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL = "http://host.docker.internal:18082"
DEFAULT_SECOPS_MOCK_AUTH_USERNAME = "admin"
DEFAULT_SECOPS_MOCK_AUTH_PASSWORD = "111111"
AUTH_HEADER = "X-Mock-Auth-Token"


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _mock_base_url() -> str:
    configured = os.getenv(SECOPS_MOCK_BACKEND_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL
    return DEFAULT_SECOPS_MOCK_BACKEND_URL


def _operator_credentials() -> tuple[str, str]:
    return (
        os.getenv(SECOPS_MOCK_AUTH_USERNAME_ENV, DEFAULT_SECOPS_MOCK_AUTH_USERNAME),
        os.getenv(SECOPS_MOCK_AUTH_PASSWORD_ENV, DEFAULT_SECOPS_MOCK_AUTH_PASSWORD),
    )


def _request_json(
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
        _mock_base_url() + path,
        data=body,
        headers=request_headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _login() -> str:
    username, password = _operator_credentials()
    body = _request_json("POST", "/api/mock/auth/login", payload={"username": username, "password": password})
    token = body.get("token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("mock auth login did not return a token")
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {AUTH_HEADER: token}


def get_context(username: str) -> dict[str, Any]:
    try:
        token = _login()
        users = _request_json("GET", "/api/mock/auth/users", headers=_auth_headers(token))
        sessions = _request_json("GET", "/api/mock/auth/sessions", headers=_auth_headers(token))
        user = next((item for item in users.get("users", []) if item.get("username") == username), None)
        active_sessions = [item for item in sessions.get("sessions", []) if item.get("username") == username]
        return {
            "ok": True,
            "username": username,
            "userExists": user is not None,
            "disabled": bool(user.get("disabled")) if user else False,
            "commonIp": str(user.get("commonIp") or "") if user else "",
            "sessions": active_sessions,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "username": username, "error": str(error)}


def kick_sessions(username: str) -> dict[str, Any]:
    try:
        token = _login()
        sessions = _request_json("GET", "/api/mock/auth/sessions", headers=_auth_headers(token))
        matching_sessions = [item for item in sessions.get("sessions", []) if item.get("username") == username]
        kicked_ids: list[str] = []
        for session in matching_sessions:
            session_id = str(session["sessionId"])
            _request_json("POST", f"/api/mock/auth/sessions/{session_id}/kick", headers=_auth_headers(token))
            kicked_ids.append(session_id)
        return {
            "ok": True,
            "username": username,
            "kickedSessionCount": len(kicked_ids),
            "kickedSessionIds": kicked_ids,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "username": username, "error": str(error)}


def disable_user(username: str) -> dict[str, Any]:
    try:
        token = _login()
        user = _request_json("POST", f"/api/mock/auth/users/{username}/disable", headers=_auth_headers(token))
        return {
            "ok": True,
            "username": username,
            "disabled": bool(user.get("disabled")),
            "user": user,
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "username": username, "error": str(error)}


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock auth skill-local operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("--username", required=True)

    kick_parser = subparsers.add_parser("kick")
    kick_parser.add_argument("--username", required=True)

    disable_parser = subparsers.add_parser("disable")
    disable_parser.add_argument("--username", required=True)

    args = parser.parse_args(argv)
    if args.command == "context":
        _print_json(get_context(args.username))
    elif args.command == "kick":
        _print_json(kick_sessions(args.username))
    elif args.command == "disable":
        _print_json(disable_user(args.username))
    return 0


if __name__ == "__main__":
    sys.exit(main())
