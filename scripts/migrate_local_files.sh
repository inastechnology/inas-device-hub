#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REPO_LOCAL_FILES=(
  ".env"
  ".camera_device_list.json"
  ".device_configs.json"
  ".device_list.json"
  ".location_list.json"
  "data"
  "logs"
)

COMMAND="${1:-}"
shift || true

SOURCE_DIR="$REPO_ROOT"
TARGET_DIR="$REPO_ROOT"
WORK_DIR="${WORK_DIR:-$HOME/.ina-device-hub}"
INCLUDE_WORK_DIR=false
DRY_RUN=false
OVERWRITE=false

usage() {
  cat <<EOF
Usage:
  $0 list [--source-dir DIR] [--work-dir DIR] [--include-work-dir]
  $0 export ARCHIVE_DIR [--source-dir DIR] [--work-dir DIR] [--include-work-dir] [--dry-run] [--overwrite]
  $0 import ARCHIVE_DIR [--target-dir DIR] [--work-dir DIR] [--include-work-dir] [--dry-run] [--overwrite]

Commands:
  list      Show local files that would be migrated
  export    Copy local files from this repository into ARCHIVE_DIR
  import    Copy local files from ARCHIVE_DIR into this repository

Options:
  --source-dir DIR       Repository directory to export from
  --target-dir DIR       Repository directory to import into
  --work-dir DIR         Runtime WORK_DIR path; default: \$WORK_DIR or ~/.ina-device-hub
  --include-work-dir     Also copy the runtime WORK_DIR into archive/work_dir
  --dry-run              Print actions without copying
  --overwrite            Replace existing files at the destination
EOF
}

fail() {
  echo "Error: $*" >&2
  exit 2
}

require_arg() {
  local name="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || fail "$name requires a value"
}

resolve_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf "%s\n" "$path"
  else
    printf "%s\n" "$(pwd)/$path"
  fi
}

copy_item() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    echo "skip missing: $src"
    return
  fi

  if [[ -e "$dst" && "$OVERWRITE" != true ]]; then
    echo "skip existing: $dst"
    return
  fi

  echo "copy: $src -> $dst"
  if [[ "$DRY_RUN" == true ]]; then
    return
  fi

  mkdir -p "$(dirname "$dst")"
  if [[ -e "$dst" && "$OVERWRITE" == true ]]; then
    rm -rf "$dst"
  fi
  cp -a "$src" "$dst"
}

print_list() {
  local base_dir="$1"
  local work_dir="$2"
  local path

  echo "Repository local files:"
  for path in "${REPO_LOCAL_FILES[@]}"; do
    if [[ -e "$base_dir/$path" ]]; then
      echo "  $base_dir/$path"
    fi
  done

  if [[ "$INCLUDE_WORK_DIR" == true ]]; then
    echo "Runtime work directory:"
    if [[ -e "$work_dir" ]]; then
      echo "  $work_dir"
    else
      echo "  missing: $work_dir"
    fi
  fi
}

parse_common_options() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source-dir)
        require_arg "$1" "${2:-}"
        SOURCE_DIR="$(resolve_path "$2")"
        shift 2
        ;;
      --target-dir)
        require_arg "$1" "${2:-}"
        TARGET_DIR="$(resolve_path "$2")"
        shift 2
        ;;
      --work-dir)
        require_arg "$1" "${2:-}"
        WORK_DIR="$(resolve_path "$2")"
        shift 2
        ;;
      --include-work-dir)
        INCLUDE_WORK_DIR=true
        shift
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --overwrite)
        OVERWRITE=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "unknown option: $1"
        ;;
    esac
  done
}

case "$COMMAND" in
  list)
    parse_common_options "$@"
    print_list "$SOURCE_DIR" "$WORK_DIR"
    ;;
  export)
    ARCHIVE_DIR="${1:-}"
    require_arg "ARCHIVE_DIR" "$ARCHIVE_DIR"
    shift
    ARCHIVE_DIR="$(resolve_path "$ARCHIVE_DIR")"
    parse_common_options "$@"

    echo "Exporting local files to: $ARCHIVE_DIR"
    for path in "${REPO_LOCAL_FILES[@]}"; do
      copy_item "$SOURCE_DIR/$path" "$ARCHIVE_DIR/repo/$path"
    done
    if [[ "$INCLUDE_WORK_DIR" == true ]]; then
      copy_item "$WORK_DIR" "$ARCHIVE_DIR/work_dir"
    fi
    ;;
  import)
    ARCHIVE_DIR="${1:-}"
    require_arg "ARCHIVE_DIR" "$ARCHIVE_DIR"
    shift
    ARCHIVE_DIR="$(resolve_path "$ARCHIVE_DIR")"
    parse_common_options "$@"

    echo "Importing local files from: $ARCHIVE_DIR"
    for path in "${REPO_LOCAL_FILES[@]}"; do
      copy_item "$ARCHIVE_DIR/repo/$path" "$TARGET_DIR/$path"
    done
    if [[ "$INCLUDE_WORK_DIR" == true ]]; then
      copy_item "$ARCHIVE_DIR/work_dir" "$WORK_DIR"
    fi
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    fail "unknown command: $COMMAND"
    ;;
esac
