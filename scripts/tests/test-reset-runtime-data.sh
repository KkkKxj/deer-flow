#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

DEER_FLOW_HOME="$TMP_DIR/.deer-flow"

mkdir -p \
    "$DEER_FLOW_HOME/data" \
    "$DEER_FLOW_HOME/channels" \
    "$DEER_FLOW_HOME/agents/secops-agent" \
    "$DEER_FLOW_HOME/users/user-1/threads/thread-1/user-data/uploads" \
    "$DEER_FLOW_HOME/users/user-1/agents/secops-agent" \
    "$DEER_FLOW_HOME/users/user-2/threads/thread-2" \
    "$DEER_FLOW_HOME/users/user-2/agents/custom-agent"

printf 'db\n' > "$DEER_FLOW_HOME/data/deerflow.db"
printf 'channel\n' > "$DEER_FLOW_HOME/channels/state.json"
printf 'checkpoint\n' > "$DEER_FLOW_HOME/checkpoints.db"
printf 'wal\n' > "$DEER_FLOW_HOME/checkpoints.db-wal"
printf 'shm\n' > "$DEER_FLOW_HOME/checkpoints.db-shm"
printf 'legacy memory\n' > "$DEER_FLOW_HOME/memory.json"
printf 'legacy agent memory\n' > "$DEER_FLOW_HOME/agents/secops-agent/memory.json"
printf 'legacy agent config\n' > "$DEER_FLOW_HOME/agents/secops-agent/config.yaml"
printf 'upload\n' > "$DEER_FLOW_HOME/users/user-1/threads/thread-1/user-data/uploads/file.txt"
printf 'user memory\n' > "$DEER_FLOW_HOME/users/user-1/memory.json"
printf 'agent memory\n' > "$DEER_FLOW_HOME/users/user-1/agents/secops-agent/memory.json"
printf 'agent config\n' > "$DEER_FLOW_HOME/users/user-1/agents/secops-agent/config.yaml"
printf 'agent soul\n' > "$DEER_FLOW_HOME/users/user-1/agents/secops-agent/SOUL.md"
printf 'other thread\n' > "$DEER_FLOW_HOME/users/user-2/threads/thread-2/state.json"
printf 'custom memory\n' > "$DEER_FLOW_HOME/users/user-2/agents/custom-agent/memory.json"
printf 'custom config\n' > "$DEER_FLOW_HOME/users/user-2/agents/custom-agent/config.yaml"
printf 'secret\n' > "$DEER_FLOW_HOME/.better-auth-secret"

DEER_FLOW_HOME="$DEER_FLOW_HOME" bash "$REPO_ROOT/scripts/reset-runtime-data.sh"

removed_paths=(
    "$DEER_FLOW_HOME/data"
    "$DEER_FLOW_HOME/channels"
    "$DEER_FLOW_HOME/checkpoints.db"
    "$DEER_FLOW_HOME/checkpoints.db-wal"
    "$DEER_FLOW_HOME/checkpoints.db-shm"
    "$DEER_FLOW_HOME/memory.json"
    "$DEER_FLOW_HOME/agents/secops-agent/memory.json"
    "$DEER_FLOW_HOME/users/user-1/threads"
    "$DEER_FLOW_HOME/users/user-1/memory.json"
    "$DEER_FLOW_HOME/users/user-1/agents/secops-agent/memory.json"
    "$DEER_FLOW_HOME/users/user-2/threads"
    "$DEER_FLOW_HOME/users/user-2/agents/custom-agent/memory.json"
)

for path in "${removed_paths[@]}"; do
    if [ -e "$path" ]; then
        printf 'expected runtime data to be removed: %s\n' "$path" >&2
        exit 1
    fi
done

preserved_paths=(
    "$DEER_FLOW_HOME/.better-auth-secret"
    "$DEER_FLOW_HOME/agents/secops-agent/config.yaml"
    "$DEER_FLOW_HOME/users/user-1/agents/secops-agent/config.yaml"
    "$DEER_FLOW_HOME/users/user-1/agents/secops-agent/SOUL.md"
    "$DEER_FLOW_HOME/users/user-2/agents/custom-agent/config.yaml"
)

for path in "${preserved_paths[@]}"; do
    if [ ! -e "$path" ]; then
        printf 'expected non-business data to be preserved: %s\n' "$path" >&2
        exit 1
    fi
done
