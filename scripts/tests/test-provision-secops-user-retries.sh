#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_REPO="$TMP_DIR/repo"
TEST_BIN="$TMP_DIR/bin"
TEST_LOG="$TMP_DIR/calls.log"
ATTEMPT_FILE="$TMP_DIR/attempts"
mkdir -p "$TEST_REPO/scripts" "$TEST_REPO/docker" "$TEST_BIN"

cp "$REPO_ROOT/scripts/provision-secops-user.sh" "$TEST_REPO/scripts/provision-secops-user.sh"
printf 'services: {}\n' > "$TEST_REPO/docker/docker-compose.yaml"
printf '0\n' > "$ATTEMPT_FILE"

cat > "$TEST_BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

attempt="$(cat "$ATTEMPT_FILE")"
attempt="$((attempt + 1))"
printf '%s\n' "$attempt" > "$ATTEMPT_FILE"
printf 'docker attempt %s: %s\n' "$attempt" "$*" >> "$TEST_LOG"

if [ "$attempt" -lt 3 ]; then
    printf 'gateway not ready\n' >&2
    exit 1
fi

printf 'Created DeerFlow fixed admin: 8818b236-7db8-451e-beb2-12a483a5ee50 1006507163@qq.com\n'
EOF

chmod +x "$TEST_BIN/docker"
export ATTEMPT_FILE TEST_LOG

PATH="$TEST_BIN:$PATH" \
    DEER_FLOW_PROVISION_MAX_ATTEMPTS=5 \
    DEER_FLOW_PROVISION_RETRY_DELAY_SECONDS=0 \
    bash "$TEST_REPO/scripts/provision-secops-user.sh" > "$TMP_DIR/stdout.log"

if [ "$(cat "$ATTEMPT_FILE")" != "3" ]; then
    printf 'expected provision script to stop after third successful attempt, got %s attempts\n' "$(cat "$ATTEMPT_FILE")" >&2
    exit 1
fi

grep -q "Created DeerFlow fixed admin" "$TMP_DIR/stdout.log"

cat > "$TMP_DIR/expected.log" <<'EOF'
docker attempt 1: compose -p deer-flow -f /tmp/COMPOSE_PATH exec -T -e SECOPS_FIXED_DEERFLOW_USER_ID=8818b236-7db8-451e-beb2-12a483a5ee50 -e SECOPS_FIXED_DEERFLOW_EMAIL=1006507163@qq.com -e SECOPS_FIXED_DEERFLOW_PASSWORD=11111111 -e DEER_FLOW_PROVISION_DB_READY_TIMEOUT_SECONDS=30 gateway sh -c cd backend && uv run --no-sync python -
docker attempt 2: compose -p deer-flow -f /tmp/COMPOSE_PATH exec -T -e SECOPS_FIXED_DEERFLOW_USER_ID=8818b236-7db8-451e-beb2-12a483a5ee50 -e SECOPS_FIXED_DEERFLOW_EMAIL=1006507163@qq.com -e SECOPS_FIXED_DEERFLOW_PASSWORD=11111111 -e DEER_FLOW_PROVISION_DB_READY_TIMEOUT_SECONDS=30 gateway sh -c cd backend && uv run --no-sync python -
docker attempt 3: compose -p deer-flow -f /tmp/COMPOSE_PATH exec -T -e SECOPS_FIXED_DEERFLOW_USER_ID=8818b236-7db8-451e-beb2-12a483a5ee50 -e SECOPS_FIXED_DEERFLOW_EMAIL=1006507163@qq.com -e SECOPS_FIXED_DEERFLOW_PASSWORD=11111111 -e DEER_FLOW_PROVISION_DB_READY_TIMEOUT_SECONDS=30 gateway sh -c cd backend && uv run --no-sync python -
EOF

sed "s#-f $TEST_REPO/docker/docker-compose.yaml#-f /tmp/COMPOSE_PATH#g" "$TEST_LOG" > "$TMP_DIR/normalized.log"
diff -u "$TMP_DIR/expected.log" "$TMP_DIR/normalized.log"
