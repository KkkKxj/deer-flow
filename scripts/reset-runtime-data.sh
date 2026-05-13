#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_ROOT/backend/.deer-flow}"

usage() {
    cat <<EOF
Usage:
  scripts/reset-runtime-data.sh

Deletes DeerFlow business runtime data under DEER_FLOW_HOME while preserving
configuration, environment files, skills, auth secrets, and agent definitions.

Environment:
  DEER_FLOW_HOME                      default: <repo>/backend/.deer-flow
  DEER_FLOW_RESET_ALLOW_CUSTOM_HOME   set to 1 to allow a DEER_FLOW_HOME whose
                                      basename is not .deer-flow
EOF
}

case "${1:-}" in
    "")
        ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown argument: $1" >&2
        usage
        exit 1
        ;;
esac

if [ ! -d "$DEER_FLOW_HOME" ]; then
    echo "No DeerFlow runtime data directory found: $DEER_FLOW_HOME"
    exit 0
fi

RESOLVED_DEER_FLOW_HOME="$(cd "$DEER_FLOW_HOME" && pwd -P)"
RESOLVED_REPO_ROOT="$(cd "$REPO_ROOT" && pwd -P)"
RESOLVED_BACKEND_DIR="$RESOLVED_REPO_ROOT/backend"

case "$RESOLVED_DEER_FLOW_HOME" in
    "/"|"/data"|"/home"|"/root"|"$RESOLVED_REPO_ROOT"|"$RESOLVED_BACKEND_DIR")
        echo "Refusing to reset unsafe DEER_FLOW_HOME: $RESOLVED_DEER_FLOW_HOME" >&2
        exit 1
        ;;
esac

if [ "${DEER_FLOW_RESET_ALLOW_CUSTOM_HOME:-0}" != "1" ] \
    && [ "$(basename "$RESOLVED_DEER_FLOW_HOME")" != ".deer-flow" ]; then
    echo "Refusing to reset DEER_FLOW_HOME whose basename is not .deer-flow: $RESOLVED_DEER_FLOW_HOME" >&2
    echo "Set DEER_FLOW_RESET_ALLOW_CUSTOM_HOME=1 if this is intentional." >&2
    exit 1
fi

remove_path() {
    local path="$1"

    if [ -e "$path" ]; then
        echo "Removing $path"
        rm -rf -- "$path"
    fi
}

shopt -s nullglob

remove_path "$RESOLVED_DEER_FLOW_HOME/data"
remove_path "$RESOLVED_DEER_FLOW_HOME/channels"
remove_path "$RESOLVED_DEER_FLOW_HOME/threads"
remove_path "$RESOLVED_DEER_FLOW_HOME/memory.json"

for checkpoint_path in "$RESOLVED_DEER_FLOW_HOME"/checkpoints.db*; do
    remove_path "$checkpoint_path"
done

for legacy_agent_dir in "$RESOLVED_DEER_FLOW_HOME"/agents/*; do
    [ -d "$legacy_agent_dir" ] || continue
    remove_path "$legacy_agent_dir/memory.json"
done

for user_dir in "$RESOLVED_DEER_FLOW_HOME"/users/*; do
    [ -d "$user_dir" ] || continue

    remove_path "$user_dir/threads"
    remove_path "$user_dir/channels"
    remove_path "$user_dir/memory.json"

    for user_agent_dir in "$user_dir"/agents/*; do
        [ -d "$user_agent_dir" ] || continue
        remove_path "$user_agent_dir/memory.json"
    done
done

echo "DeerFlow runtime business data reset under $RESOLVED_DEER_FLOW_HOME"
