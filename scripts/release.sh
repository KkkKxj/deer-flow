#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_REPO="${DEER_FLOW_IMAGE_REPO:-kkk2099/kkk}"
IMAGE_VERSION_FILE="$REPO_ROOT/.image-version"
IMAGE_VERSION=""
REGISTRY_SERVICES="${DEER_FLOW_REGISTRY_SERVICES:-frontend gateway}"
AUTO_GIT="${DEER_FLOW_RELEASE_GIT:-1}"

usage() {
    cat <<EOF
Usage:
  scripts/release.sh
  scripts/release.sh release
      Build with the native deploy script, auto-bump patch version, tag images,
      then push them to the registry.

  scripts/release.sh build
      Build images with the native deploy script only.

  scripts/release.sh push
      Tag current local images and push them to the registry.

  scripts/release.sh pull
      Pull registry images and tag them back to native local image names.

  scripts/release.sh up
      Pull/tag registry images, then start with the native deploy script
      without rebuilding, then provision the fixed SecOps user.

  scripts/release.sh start
      Start with the native deploy script without pull/build, then provision
      the fixed SecOps user.

  scripts/release.sh down
      Stop with the native deploy script.

  scripts/release.sh images
      Print local-to-registry image mapping.

Environment:
  DEER_FLOW_IMAGE_REPO          default: kkk2099/kkk
  DEER_FLOW_REGISTRY_SERVICES   default: frontend gateway
  DEER_FLOW_RELEASE_GIT         commit and push .image-version after release, default: 1

Examples:
  scripts/release.sh
  scripts/release.sh up
  DEER_FLOW_REGISTRY_SERVICES="frontend gateway provisioner" scripts/release.sh
EOF
}

read_file_version() {
    if [ -f "$IMAGE_VERSION_FILE" ]; then
        tr -d '[:space:]' < "$IMAGE_VERSION_FILE"
    else
        printf '%s\n' "1.0.0"
    fi
}

validate_version() {
    local version="$1"
    local old_ifs=$IFS
    IFS=.
    set -- $version
    IFS=$old_ifs

    [ "$#" -eq 3 ] || return 1
    case "$1$2$3" in
        ""|*[!0-9]*) return 1 ;;
    esac
}

next_patch_version() {
    local version="$1"
    local old_ifs=$IFS
    IFS=.
    set -- $version
    IFS=$old_ifs

    printf '%s.%s.%s\n' "$1" "$2" "$(($3 + 1))"
}

resolve_image_version() {
    read_file_version
}

resolve_release_version() {
    next_patch_version "$(read_file_version)"
}

set_image_version() {
    IMAGE_VERSION="$1"
    validate_version "$IMAGE_VERSION" || {
        echo "Invalid image version: $IMAGE_VERSION" >&2
        exit 1
    }
}

write_image_version() {
    local version="$1"
    validate_version "$version" || {
        echo "Invalid image version: $version" >&2
        exit 1
    }
    printf '%s\n' "$version" > "$IMAGE_VERSION_FILE"
}

ensure_env_file() {
    local target="$1"
    local source="$2"

    if [ -f "$target" ]; then
        return
    fi

    if [ ! -f "$source" ]; then
        echo "Missing required env file: $target" >&2
        echo "Template not found: $source" >&2
        exit 1
    fi

    cp "$source" "$target"
    echo "Created $target from $source"
}

ensure_runtime_env_files() {
    ensure_env_file "$REPO_ROOT/.env" "$REPO_ROOT/.env.example"
    ensure_env_file "$REPO_ROOT/frontend/.env" "$REPO_ROOT/frontend/.env.example"
}

sync_release_branch() {
    if [ "$AUTO_GIT" = "0" ]; then
        echo "Skipped git pull because DEER_FLOW_RELEASE_GIT=0"
        return
    fi

    if ! command -v git >/dev/null 2>&1; then
        echo "git is required to sync $IMAGE_VERSION_FILE before release" >&2
        exit 1
    fi

    git pull --ff-only
}

commit_and_push_version() {
    if [ "$AUTO_GIT" = "0" ]; then
        echo "Skipped git commit/push because DEER_FLOW_RELEASE_GIT=0"
        return
    fi

    if ! command -v git >/dev/null 2>&1; then
        echo "git is required to persist $IMAGE_VERSION_FILE after release" >&2
        exit 1
    fi

    git add -- "$IMAGE_VERSION_FILE"
    if git diff --cached --quiet -- "$IMAGE_VERSION_FILE"; then
        echo "No image version changes to commit"
        return
    fi
    git commit --only "$IMAGE_VERSION_FILE" -m "Bump DeerFlow image version to $IMAGE_VERSION"
    git push
}

local_image() {
    printf 'deer-flow-%s' "$1"
}

remote_image() {
    printf '%s:deer-flow-%s-%s' "$IMAGE_REPO" "$1" "$IMAGE_VERSION"
}

print_images() {
    for service in $REGISTRY_SERVICES; do
        printf '%-24s -> %s\n' "$(local_image "$service")" "$(remote_image "$service")"
    done
}

tag_for_push() {
    for service in $REGISTRY_SERVICES; do
        docker image inspect "$(local_image "$service")" >/dev/null
        docker tag "$(local_image "$service")" "$(remote_image "$service")"
    done
}

push_images() {
    tag_for_push
    for service in $REGISTRY_SERVICES; do
        docker push "$(remote_image "$service")"
    done
}

pull_images() {
    for service in $REGISTRY_SERVICES; do
        docker pull "$(remote_image "$service")"
        docker tag "$(remote_image "$service")" "$(local_image "$service")"
    done
}

cd "$REPO_ROOT"
set_image_version "$(resolve_image_version)"

case "${1:-release}" in
    release)
        sync_release_branch
        release_version="$(resolve_release_version)"
        set_image_version "$release_version"
        echo "Releasing DeerFlow image version: $IMAGE_VERSION"
        ensure_runtime_env_files
        "$REPO_ROOT/scripts/deploy.sh" build
        push_images
        write_image_version "$IMAGE_VERSION"
        echo "Updated $IMAGE_VERSION_FILE to $IMAGE_VERSION"
        commit_and_push_version
        ;;
    build)
        ensure_runtime_env_files
        "$REPO_ROOT/scripts/deploy.sh" build
        ;;
    push)
        push_images
        ;;
    pull)
        pull_images
        ;;
    up)
        pull_images
        ensure_runtime_env_files
        "$REPO_ROOT/scripts/deploy.sh" start
        bash "$REPO_ROOT/scripts/provision-secops-user.sh"
        ;;
    start)
        ensure_runtime_env_files
        "$REPO_ROOT/scripts/deploy.sh" start
        bash "$REPO_ROOT/scripts/provision-secops-user.sh"
        ;;
    down)
        ensure_runtime_env_files
        "$REPO_ROOT/scripts/deploy.sh" down
        ;;
    images)
        print_images
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: $1" >&2
        usage
        exit 1
        ;;
esac
