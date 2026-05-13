#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_REPO="$TMP_DIR/repo"
TEST_LOG="$TMP_DIR/calls.log"
mkdir -p "$TEST_REPO/scripts" "$TEST_REPO/frontend"

cp "$REPO_ROOT/scripts/release.sh" "$TEST_REPO/scripts/release.sh"
printf '1.0.0\n' > "$TEST_REPO/.image-version"
printf 'AUTH_JWT_SECRET=existing-secret\n' > "$TEST_REPO/.env"
printf 'FRONTEND_ENV=present\n' > "$TEST_REPO/frontend/.env"

cat > "$TEST_REPO/scripts/deploy.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'deploy %s\n' "$*" >> "$TEST_LOG"
EOF

cat > "$TEST_REPO/scripts/reset-runtime-data.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'reset-runtime-data\n' >> "$TEST_LOG"
EOF

chmod +x "$TEST_REPO/scripts/deploy.sh" "$TEST_REPO/scripts/reset-runtime-data.sh"
export TEST_LOG

bash "$TEST_REPO/scripts/release.sh" reset-data

cat > "$TMP_DIR/expected.log" <<'EOF'
deploy down
reset-runtime-data
EOF

diff -u "$TMP_DIR/expected.log" "$TEST_LOG"
