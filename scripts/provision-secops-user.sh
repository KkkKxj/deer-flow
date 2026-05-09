#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.yaml"

SECOPS_FIXED_DEERFLOW_USER_ID="8818b236-7db8-451e-beb2-12a483a5ee50"
SECOPS_FIXED_DEERFLOW_EMAIL="1006507163@qq.com"
SECOPS_FIXED_DEERFLOW_PASSWORD="11111111"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Missing DeerFlow compose file: $COMPOSE_FILE" >&2
    exit 1
fi

export DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_ROOT/backend/.deer-flow}"
export DEER_FLOW_CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-$REPO_ROOT/config.yaml}"
export DEER_FLOW_EXTENSIONS_CONFIG_PATH="${DEER_FLOW_EXTENSIONS_CONFIG_PATH:-$REPO_ROOT/extensions_config.json}"
export DEER_FLOW_DOCKER_SOCKET="${DEER_FLOW_DOCKER_SOCKET:-/var/run/docker.sock}"
export DEER_FLOW_REPO_ROOT="${DEER_FLOW_REPO_ROOT:-$REPO_ROOT}"

if [ -z "${BETTER_AUTH_SECRET:-}" ] && [ -f "$DEER_FLOW_HOME/.better-auth-secret" ]; then
    BETTER_AUTH_SECRET="$(cat "$DEER_FLOW_HOME/.better-auth-secret")"
fi
export BETTER_AUTH_SECRET="${BETTER_AUTH_SECRET:-placeholder}"

docker compose -p deer-flow -f "$COMPOSE_FILE" exec -T \
    -e SECOPS_FIXED_DEERFLOW_USER_ID="$SECOPS_FIXED_DEERFLOW_USER_ID" \
    -e SECOPS_FIXED_DEERFLOW_EMAIL="$SECOPS_FIXED_DEERFLOW_EMAIL" \
    -e SECOPS_FIXED_DEERFLOW_PASSWORD="$SECOPS_FIXED_DEERFLOW_PASSWORD" \
    gateway sh -c "cd backend && uv run --no-sync python -" <<'PY'
import base64
import datetime as dt
import hashlib
import os
import sqlite3
import sys
import time

import bcrypt

db_path = "/app/backend/.deer-flow/data/deerflow.db"
user_id = os.environ["SECOPS_FIXED_DEERFLOW_USER_ID"]
email = os.environ["SECOPS_FIXED_DEERFLOW_EMAIL"]
password = os.environ["SECOPS_FIXED_DEERFLOW_PASSWORD"]

deadline = time.monotonic() + 30
conn = sqlite3.connect(db_path)
try:
    while True:
        table = conn.execute(
            "select 1 from sqlite_master where type='table' and name='users'"
        ).fetchone()
        if table:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("DeerFlow users table is not ready")
        time.sleep(1)

    row = conn.execute("select 1 from users where id=?", (user_id,)).fetchone()
    if row:
        print(f"DeerFlow fixed user exists: {user_id}")
        sys.exit(0)

    digest = base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    password_hash = "$dfv2$" + bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")
    created_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()

    conn.execute(
        "insert into users (id, email, password_hash, system_role, created_at, oauth_provider, oauth_id, needs_setup, token_version) values (?, ?, ?, ?, ?, NULL, NULL, 0, 0)",
        (user_id, email, password_hash, "user", created_at),
    )
    conn.commit()
    print(f"Created DeerFlow fixed user: {user_id} {email}")
finally:
    conn.close()
PY
