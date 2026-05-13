#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_REPO="$TMP_DIR/repo"
TEST_BIN="$TMP_DIR/bin"
TEST_LOG="$TMP_DIR/calls.log"
mkdir -p "$TEST_REPO/scripts" "$TEST_REPO/frontend" "$TEST_BIN"

cp "$REPO_ROOT/scripts/release.sh" "$TEST_REPO/scripts/release.sh"
printf '1.0.0\n' > "$TEST_REPO/.image-version"
printf 'AUTH_JWT_SECRET=existing-secret\n' > "$TEST_REPO/.env"
printf 'FRONTEND_ENV=present\n' > "$TEST_REPO/frontend/.env"

cat > "$TEST_REPO/scripts/deploy.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

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
    "tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway")
        ;;
    *)
        printf 'unexpected docker arguments: %s\n' "$*" >&2
        exit 1
        ;;
esac
EOF

chmod +x "$TEST_REPO/scripts/deploy.sh" "$TEST_REPO/scripts/provision-secops-user.sh"
chmod +x "$TEST_BIN/git" "$TEST_BIN/docker"
export TEST_REPO TEST_LOG
PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" up

cat > "$TMP_DIR/expected.log" <<'EOF'
git pull --ff-only
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
deploy start
provision
EOF

diff -u "$TMP_DIR/expected.log" "$TEST_LOG"
