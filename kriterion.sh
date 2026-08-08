#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${KRITERION_PYTHON:-$SCRIPT_DIR/.venv/bin/python}"

CVS_DIR="./cvs"
PROFILE_PATH="./profiles/profile.yaml"
OUTPUT_DIR="."
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage: ./kriterion.sh [options]

Runs Kriterion screening and keeps its dashboard server in the foreground.

Path options:
  --cvs-dir PATH       CV directory (default: ./cvs)
  --profile PATH       Profile YAML (default: ./profiles/profile.yaml)
  --output-dir PATH    Report parent directory (default: .)

Common forwarded options:
  --no-open            Do not open the dashboard automatically
  --no-auto-ai         Do not request ambiguous AI recommendations automatically
  --no-cache           Rescreen every CV and discard saved AI reviews
  --min-devops-years N Override the profile's minimum experience
  --required-keyword K Override required experience keywords (repeatable)
  --min-score N        Override the profile's minimum score
  -v, --verbose        Print per-CV screening details
  -h, --help           Show this help

Any other option is forwarded to kriterion.py.
EOF
}

require_value() {
  if [[ $# -lt 2 || -z "$2" ]]; then
    printf 'kriterion: %s requires a value\n' "$1" >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cvs-dir)
      require_value "$1" "${2-}"
      CVS_DIR="$2"
      shift 2
      ;;
    --cvs-dir=*)
      CVS_DIR="${1#*=}"
      shift
      ;;
    --profile)
      require_value "$1" "${2-}"
      PROFILE_PATH="$2"
      shift 2
      ;;
    --profile=*)
      PROFILE_PATH="${1#*=}"
      shift
      ;;
    --output-dir)
      require_value "$1" "${2-}"
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

exec "$PYTHON" "$SCRIPT_DIR/kriterion.py" \
  "$CVS_DIR" \
  --profile "$PROFILE_PATH" \
  --output-dir "$OUTPUT_DIR" \
  "${EXTRA_ARGS[@]}"
