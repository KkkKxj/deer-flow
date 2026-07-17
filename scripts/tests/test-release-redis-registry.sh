#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_REPO="$TMP_DIR/repo"
TEST_BIN="$TMP_DIR/bin"
TEST_LOG="$TMP_DIR/docker.log"
mkdir -p "$TEST_REPO/scripts" "$TEST_BIN"
cp "$REPO_ROOT/scripts/release.sh" "$TEST_REPO/scripts/release.sh"
printf '2.0.0\n' > "$TEST_REPO/.image-version"

cat > "$TEST_BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'docker %s\n' "$*" >> "$TEST_LOG"
EOF
chmod +x "$TEST_BIN/docker"
export TEST_LOG

PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" push
cat > "$TMP_DIR/expected-push.log" <<'EOF'
docker image inspect deer-flow-frontend
docker tag deer-flow-frontend kkk2099/kkk:deer-flow-frontend-2.0.0
docker image inspect deer-flow-gateway
docker tag deer-flow-gateway kkk2099/kkk:deer-flow-gateway-2.0.0
docker push kkk2099/kkk:deer-flow-frontend-2.0.0
docker push kkk2099/kkk:deer-flow-gateway-2.0.0
docker pull redis:7-alpine
docker tag redis:7-alpine kkk2099/kkk:redis-7-alpine
docker push kkk2099/kkk:redis-7-alpine
EOF
diff -u "$TMP_DIR/expected-push.log" "$TEST_LOG"

: > "$TEST_LOG"
PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" pull
cat > "$TMP_DIR/expected-pull.log" <<'EOF'
docker pull kkk2099/kkk:deer-flow-frontend-2.0.0
docker tag kkk2099/kkk:deer-flow-frontend-2.0.0 deer-flow-frontend
docker pull kkk2099/kkk:deer-flow-gateway-2.0.0
docker tag kkk2099/kkk:deer-flow-gateway-2.0.0 deer-flow-gateway
docker pull kkk2099/kkk:redis-7-alpine
docker tag kkk2099/kkk:redis-7-alpine redis:7-alpine
EOF
diff -u "$TMP_DIR/expected-pull.log" "$TEST_LOG"

PATH="$TEST_BIN:$PATH" bash "$TEST_REPO/scripts/release.sh" images \
    > "$TMP_DIR/images.out"
grep -F 'redis:7-alpine' "$TMP_DIR/images.out" >/dev/null
grep -F 'kkk2099/kkk:redis-7-alpine' "$TMP_DIR/images.out" >/dev/null
