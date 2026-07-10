#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_REPO="$TMP_DIR/repo"
TEST_BIN="$TMP_DIR/bin"
TEST_LOG="$TMP_DIR/calls.log"
AUTH_STATUS_FILE="$TMP_DIR/better-auth-status"
EXPECTED_BETTER_AUTH_FILE="$TMP_DIR/expected-better-auth"
DEER_FLOW_HOME="$TMP_DIR/runtime-home"
CONFIGURED_BETTER_AUTH_SECRET="better-auth-test-$$"
mkdir -p "$TEST_REPO/scripts" "$TEST_REPO/frontend" "$TEST_BIN"

cp "$REPO_ROOT/scripts/release.sh" "$TEST_REPO/scripts/release.sh"
printf '1.0.0\n' > "$TEST_REPO/.image-version"
printf 'AUTH_JWT_SECRET=existing-secret\nBETTER_AUTH_SECRET=%s\n' \
    "$CONFIGURED_BETTER_AUTH_SECRET" > "$TEST_REPO/.env"
printf '%s\n' "$CONFIGURED_BETTER_AUTH_SECRET" > "$EXPECTED_BETTER_AUTH_FILE"
printf 'FRONTEND_ENV=present\n' > "$TEST_REPO/frontend/.env"

cat > "$TEST_REPO/scripts/deploy.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

secret_file="$DEER_FLOW_HOME/.better-auth-secret"
mkdir -p "$DEER_FLOW_HOME"
if [ -z "${BETTER_AUTH_SECRET:-}" ]; then
    if [ -f "$secret_file" ]; then
        BETTER_AUTH_SECRET="$(cat "$secret_file")"
    else
        BETTER_AUTH_SECRET="native-generated-for-test"
        printf '%s\n' "$BETTER_AUTH_SECRET" > "$secret_file"
        chmod 600 "$secret_file"
    fi
    export BETTER_AUTH_SECRET
fi

expected_better_auth_secret="$(cat "$EXPECTED_BETTER_AUTH_FILE")"
if [ "$BETTER_AUTH_SECRET" = "$expected_better_auth_secret" ] \
    && cmp -s "$EXPECTED_BETTER_AUTH_FILE" "$secret_file"; then
    printf 'MATCH\n' > "$AUTH_STATUS_FILE"
else
    printf 'MISMATCH\n' > "$AUTH_STATUS_FILE"
fi

printf 'deploy %s\n' "$*" >> "$TEST_LOG"
EOF

cat > "$TEST_REPO/scripts/provision-secops-user.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'provision\n' >> "$TEST_LOG"
EOF

cat > "$TEST_BIN/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'git %s\n' "$*" >> "$TEST_LOG"
if [ "$*" = "pull --ff-only" ]; then
    printf '2.0.0\n' > "$TEST_REPO/.image-version"
    exit 0
fi

printf 'unexpected git arguments: %s\n' "$*" >&2
exit 1
EOF

cat > "$TEST_BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'docker %s\n' "$*" >> "$TEST_LOG"
case "$*" in
    "pull kkk2099/kkk:deer-flow-frontend-2.0.0"|\
    "tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend"|\
    "pull kkk2099/kkk:deer-flow-gateway-2.0.0"|\
    "tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway"|\
    "network create secops-deerflow")
        ;;
    "network connect --alias deer-flow-nginx secops-deerflow deer-flow-nginx")
        if [ "${FAILING_NETWORK_CONNECT_CONTAINER:-}" = "deer-flow-nginx" ]; then
            echo "Failed to connect deer-flow-nginx to secops-deerflow" >&2
            exit 1
        fi
        ;;
    "network connect --alias deer-flow-gateway secops-deerflow deer-flow-gateway")
        if [ "${FAILING_NETWORK_CONNECT_CONTAINER:-}" = "deer-flow-gateway" ]; then
            echo "Failed to connect deer-flow-gateway to secops-deerflow" >&2
            exit 1
        fi
        ;;
    "container inspect deer-flow-nginx")
        if [ "${MISSING_DOCKER_CONTAINER:-}" = "deer-flow-nginx" ]; then
            echo "No such container: deer-flow-nginx" >&2
            exit 1
        fi
        ;;
    "container inspect deer-flow-gateway")
        if [ "${MISSING_DOCKER_CONTAINER:-}" = "deer-flow-gateway" ]; then
            echo "No such container: deer-flow-gateway" >&2
            exit 1
        fi
        ;;
    "network inspect secops-deerflow")
        exit 1
        ;;
    "inspect deer-flow-nginx --format {{range \$name, \$_ := .NetworkSettings.Networks}}{{println \$name}}{{end}}")
        if [ "${FAILING_DOCKER_INSPECT_CONTAINER:-}" = "deer-flow-nginx" ]; then
            echo "Failed to inspect networks for deer-flow-nginx" >&2
            exit 1
        fi
        case " ${CONNECTED_DOCKER_CONTAINERS:-} " in
            *" deer-flow-nginx "*) printf '%s\n' secops-deerflow ;;
            *) printf '%s\n' deer-flow_default ;;
        esac
        ;;
    "inspect deer-flow-gateway --format {{range \$name, \$_ := .NetworkSettings.Networks}}{{println \$name}}{{end}}")
        if [ "${FAILING_DOCKER_INSPECT_CONTAINER:-}" = "deer-flow-gateway" ]; then
            echo "Failed to inspect networks for deer-flow-gateway" >&2
            exit 1
        fi
        case " ${CONNECTED_DOCKER_CONTAINERS:-} " in
            *" deer-flow-gateway "*) printf '%s\n' secops-deerflow ;;
            *) printf '%s\n' deer-flow_default ;;
        esac
        ;;
    *)
        printf 'unexpected docker arguments: %s\n' "$*" >&2
        exit 1
        ;;
esac
EOF

chmod +x "$TEST_REPO/scripts/deploy.sh" "$TEST_REPO/scripts/provision-secops-user.sh"
chmod +x "$TEST_BIN/git" "$TEST_BIN/docker"
export TEST_REPO TEST_LOG AUTH_STATUS_FILE EXPECTED_BETTER_AUTH_FILE DEER_FLOW_HOME
status=0
unset BETTER_AUTH_SECRET

rm -rf "$DEER_FLOW_HOME"
: > "$TEST_LOG"
bash "$TEST_REPO/scripts/deploy.sh" start
if [ "$(cat "$AUTH_STATUS_FILE")" != "MISMATCH" ]; then
    echo "native deploy unexpectedly consumed the root Better Auth configuration" >&2
    status=1
fi

rm -rf "$DEER_FLOW_HOME"
: > "$TEST_LOG"
NORMAL_STDOUT="$TMP_DIR/normal-up.out"
NORMAL_STDERR="$TMP_DIR/normal-up.err"
PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" up \
    > "$NORMAL_STDOUT" 2> "$NORMAL_STDERR"
if grep -Fq "$CONFIGURED_BETTER_AUTH_SECRET" "$NORMAL_STDOUT" "$NORMAL_STDERR"; then
    echo "release up exposed the Better Auth secret" >&2
    status=1
fi

cat > "$TMP_DIR/expected.log" <<'EOF'
git pull --ff-only
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
deploy start
docker network inspect secops-deerflow
docker network create secops-deerflow
docker container inspect deer-flow-nginx
docker inspect deer-flow-nginx --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-nginx secops-deerflow deer-flow-nginx
docker container inspect deer-flow-gateway
docker inspect deer-flow-gateway --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-gateway secops-deerflow deer-flow-gateway
provision
EOF

diff -u "$TMP_DIR/expected.log" "$TEST_LOG" || status=1
if [ "$(cat "$AUTH_STATUS_FILE")" != "MATCH" ]; then
    echo "release wrapper did not preserve the configured Better Auth secret" >&2
    status=1
fi
if ! cmp -s "$EXPECTED_BETTER_AUTH_FILE" "$DEER_FLOW_HOME/.better-auth-secret"; then
    echo "persisted Better Auth secret does not match the root configuration" >&2
    status=1
fi
if [ "$(stat -c '%a' "$DEER_FLOW_HOME/.better-auth-secret")" != "600" ]; then
    echo "persisted Better Auth secret does not have mode 600" >&2
    status=1
fi

: > "$TEST_LOG"
if ! PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" start; then
    echo "release start unexpectedly failed" >&2
    status=1
fi

cat > "$TMP_DIR/expected-start.log" <<'EOF'
deploy start
docker network inspect secops-deerflow
docker network create secops-deerflow
docker container inspect deer-flow-nginx
docker inspect deer-flow-nginx --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-nginx secops-deerflow deer-flow-nginx
docker container inspect deer-flow-gateway
docker inspect deer-flow-gateway --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-gateway secops-deerflow deer-flow-gateway
provision
EOF

diff -u "$TMP_DIR/expected-start.log" "$TEST_LOG" || status=1
if grep -Eq '^(git |docker (pull|tag) )' "$TEST_LOG"; then
    echo "release start unexpectedly synced git or registry images" >&2
    status=1
fi

: > "$TEST_LOG"
CONNECT_ERROR="$TMP_DIR/network-connect.err"
if FAILING_NETWORK_CONNECT_CONTAINER=deer-flow-nginx PATH="$TEST_BIN:$PATH" \
    bash "$TEST_REPO/scripts/release.sh" up 2> "$CONNECT_ERROR"; then
    echo "release up unexpectedly ignored a deer-flow-nginx network connect failure" >&2
    status=1
fi

if ! grep -Fx "Failed to connect deer-flow-nginx to secops-deerflow" "$CONNECT_ERROR" >/dev/null; then
    echo "release up hid the deer-flow-nginx network connect error" >&2
    status=1
fi

cat > "$TMP_DIR/expected-connect-failure.log" <<'EOF'
git pull --ff-only
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
deploy start
docker network inspect secops-deerflow
docker network create secops-deerflow
docker container inspect deer-flow-nginx
docker inspect deer-flow-nginx --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-nginx secops-deerflow deer-flow-nginx
EOF

diff -u "$TMP_DIR/expected-connect-failure.log" "$TEST_LOG" || status=1
if grep -Eq '^(docker (container inspect|inspect|network connect).*deer-flow-gateway|provision)$' "$TEST_LOG"; then
    echo "release up continued after the deer-flow-nginx network connect failure" >&2
    status=1
fi

: > "$TEST_LOG"
MISSING_CONTAINER_ERROR="$TMP_DIR/missing-container.err"
if MISSING_DOCKER_CONTAINER=deer-flow-gateway PATH="$TEST_BIN:$PATH" \
    bash "$TEST_REPO/scripts/release.sh" up 2> "$MISSING_CONTAINER_ERROR"; then
    echo "release up unexpectedly succeeded without deer-flow-gateway" >&2
    status=1
fi

if ! grep -Fx "No such container: deer-flow-gateway" "$MISSING_CONTAINER_ERROR" >/dev/null; then
    echo "release up hid the missing deer-flow-gateway error" >&2
    status=1
fi

cat > "$TMP_DIR/expected-missing-container.log" <<'EOF'
git pull --ff-only
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
deploy start
docker network inspect secops-deerflow
docker network create secops-deerflow
docker container inspect deer-flow-nginx
docker inspect deer-flow-nginx --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-nginx secops-deerflow deer-flow-nginx
docker container inspect deer-flow-gateway
EOF

diff -u "$TMP_DIR/expected-missing-container.log" "$TEST_LOG" || status=1

: > "$TEST_LOG"
INSPECT_ERROR="$TMP_DIR/network-inspect.err"
if FAILING_DOCKER_INSPECT_CONTAINER=deer-flow-gateway PATH="$TEST_BIN:$PATH" \
    bash "$TEST_REPO/scripts/release.sh" up 2> "$INSPECT_ERROR"; then
    echo "release up unexpectedly ignored a deer-flow-gateway network inspect failure" >&2
    status=1
fi

if ! grep -Fx "Failed to inspect networks for deer-flow-gateway" "$INSPECT_ERROR" >/dev/null; then
    echo "release up hid the deer-flow-gateway network inspect error" >&2
    status=1
fi

cat > "$TMP_DIR/expected-inspect-failure.log" <<'EOF'
git pull --ff-only
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
deploy start
docker network inspect secops-deerflow
docker network create secops-deerflow
docker container inspect deer-flow-nginx
docker inspect deer-flow-nginx --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker network connect --alias deer-flow-nginx secops-deerflow deer-flow-nginx
docker container inspect deer-flow-gateway
docker inspect deer-flow-gateway --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
EOF

diff -u "$TMP_DIR/expected-inspect-failure.log" "$TEST_LOG" || status=1

: > "$TEST_LOG"
CONNECTED_DOCKER_CONTAINERS="deer-flow-nginx deer-flow-gateway" PATH="$TEST_BIN:$PATH" \
    bash "$TEST_REPO/scripts/release.sh" up

cat > "$TMP_DIR/expected-already-connected.log" <<'EOF'
git pull --ff-only
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
deploy start
docker network inspect secops-deerflow
docker network create secops-deerflow
docker container inspect deer-flow-nginx
docker inspect deer-flow-nginx --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
docker container inspect deer-flow-gateway
docker inspect deer-flow-gateway --format {{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}
provision
EOF

diff -u "$TMP_DIR/expected-already-connected.log" "$TEST_LOG" || status=1

assert_invalid_better_auth_env() {
    local case_name="$1"
    local command

    for command in build up start; do
        : > "$TEST_LOG"
        local stdout_file="$TMP_DIR/${case_name}-${command}.out"
        local stderr_file="$TMP_DIR/${case_name}-${command}.err"
        if PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" "$command" \
            > "$stdout_file" 2> "$stderr_file"; then
            echo "release $command unexpectedly accepted $case_name BETTER_AUTH_SECRET" >&2
            status=1
        fi

        if ! grep -Fx \
            "root .env must contain exactly one non-empty BETTER_AUTH_SECRET assignment" \
            "$stderr_file" >/dev/null; then
            echo "release $command did not report the $case_name BETTER_AUTH_SECRET error" >&2
            status=1
        fi
        if grep -Eq '^(deploy |provision$)' "$TEST_LOG"; then
            echo "release $command continued to deploy or provision with $case_name BETTER_AUTH_SECRET" >&2
            status=1
        fi
        if grep -Fq "$CONFIGURED_BETTER_AUTH_SECRET" "$stdout_file" "$stderr_file"; then
            echo "release $command exposed the Better Auth secret" >&2
            status=1
        fi
    done
}

printf 'AUTH_JWT_SECRET=existing-secret\n' > "$TEST_REPO/.env"
assert_invalid_better_auth_env missing

printf 'AUTH_JWT_SECRET=existing-secret\nBETTER_AUTH_SECRET=%s\nBETTER_AUTH_SECRET=%s\n' \
    "$CONFIGURED_BETTER_AUTH_SECRET" "$CONFIGURED_BETTER_AUTH_SECRET" > "$TEST_REPO/.env"
assert_invalid_better_auth_env duplicate

exit "$status"
