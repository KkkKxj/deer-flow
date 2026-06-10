#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

grep -F 'image: ${DEER_FLOW_NGINX_IMAGE:-nginx:alpine}' "$REPO_ROOT/docker/docker-compose.yaml" >/dev/null
