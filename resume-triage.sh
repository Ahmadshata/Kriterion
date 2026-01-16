#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Simple TUI styling
# -----------------------------
ESC=$'\033'
RESET="${ESC}[0m"
BOLD="${ESC}[1m"
DIM="${ESC}[2m"

RED="${ESC}[31m"
GREEN="${ESC}[32m"
YELLOW="${ESC}[33m"
CYAN="${ESC}[36m"
WHITE="${ESC}[37m"

hr() {
  local w="${COLUMNS:-80}"
  printf "${DIM}%*s${RESET}\n" "$w" "" | tr " " "─" >&2
}

title() {
  hr
  printf "${BOLD}${CYAN}%s${RESET}\n" "$1" >&2
  hr
}

ok()   { printf "${GREEN}✔ %s${RESET}\n" "$1" >&2; }
warn() { printf "${YELLOW}⚠ %s${RESET}\n" "$1" >&2; }
err()  { printf "${RED}✖ %s${RESET}\n" "$1" >&2; }

trim() {
  # trims leading/trailing whitespace
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf "%s" "$s"
}

prompt_value() {
  # Prints prompt to stderr; returns chosen value on stdout (safe for command substitution).
  # $1 label, $2 default
  local label="$1"
  local def="$2"
  local ans=""

  printf "${BOLD}${WHITE}%s${RESET} ${DIM}(default: %s)${RESET}\n> " "$label" "$def" >&2
  IFS= read -r ans || true
  ans="$(trim "$ans")"

  if [[ -z "$ans" ]]; then
    printf "%s" "$def"
  else
    printf "%s" "$ans"
  fi
}

confirm_yn() {
  # $1 question
  local q="$1"
  local yn=""
  while true; do
    printf "${BOLD}${WHITE}%s${RESET} ${DIM}[y/n]${RESET}\n> " "$q" >&2
    IFS= read -r yn || true
    yn="$(trim "$yn")"
    case "${yn,,}" in
      y|yes) return 0 ;;
      n|no)  return 1 ;;
      *) warn "Please answer y or n." ;;
    esac
  done
}

is_number() {
  # Accepts integer or decimal (e.g., 3 or 3.0 or 2.75)
  [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

# -----------------------------
# Main
# -----------------------------
CVS_DIR="${1:-./cvs}"  # no prompt; pass as arg or default to ./cvs

DEFAULT_MIN_YEARS="3.0"
DEFAULT_KEYWORDS="Kubernetes,AWS"
DEFAULT_OUT_DIR="."

title "CV Screening CLI"
printf "${DIM}CV folder: %s${RESET}\n\n" "$CVS_DIR" >&2

# Prompt: minimum DevOps years
MIN_YEARS="$(prompt_value "Minimum DevOps years required" "$DEFAULT_MIN_YEARS")"
while ! is_number "$MIN_YEARS"; do
  warn "Invalid number: '$MIN_YEARS' (examples: 3, 3.0, 2.75)"
  MIN_YEARS="$(prompt_value "Minimum DevOps years required" "$DEFAULT_MIN_YEARS")"
done

# Prompt: required keywords
printf "${BOLD}${WHITE}Required keywords (must appear in Experience)${RESET}\n" >&2
printf "${DIM}Enter comma-separated values (example: Kubernetes,AWS,Terrraform).${RESET}\n" >&2
KEYWORDS_RAW="$(prompt_value "Keywords" "$DEFAULT_KEYWORDS")"

# Normalize keywords: commas -> spaces, split, trim, drop empties
KEYWORDS_RAW="${KEYWORDS_RAW//,/ }"
read -r -a KEYWORDS_ARR <<< "$KEYWORDS_RAW"

KEYWORDS_CLEAN=()
for kw in "${KEYWORDS_ARR[@]}"; do
  kw="$(trim "$kw")"
  [[ -n "$kw" ]] && KEYWORDS_CLEAN+=("$kw")
done

if [[ "${#KEYWORDS_CLEAN[@]}" -eq 0 ]]; then
  err "You must provide at least one keyword."
  exit 1
fi

# Prompt: output directory (default is current directory ".")
OUT_DIR="$(prompt_value "Output directory" "$DEFAULT_OUT_DIR")"
OUT_DIR="$(trim "$OUT_DIR")"
[[ -z "$OUT_DIR" ]] && OUT_DIR="."

printf "\n" >&2
title "Run Summary"
printf "${BOLD}${WHITE}CV folder:${RESET} %s\n" "$CVS_DIR" >&2
printf "${BOLD}${WHITE}Output dir:${RESET} %s\n" "$OUT_DIR" >&2
printf "${BOLD}${WHITE}Min DevOps years:${RESET} %s\n" "$MIN_YEARS" >&2
printf "${BOLD}${WHITE}Required keywords:${RESET} %s\n\n" "${KEYWORDS_CLEAN[*]}" >&2

if ! confirm_yn "Proceed to run screening now?"; then
  warn "Cancelled."
  exit 0
fi

# Build Python args
PY_ARGS=( "$CVS_DIR" "--output-dir" "$OUT_DIR" "--min-devops-years" "$MIN_YEARS" )
for kw in "${KEYWORDS_CLEAN[@]}"; do
  PY_ARGS+=( "--required-keyword" "$kw" )
done

title "Running"
printf "${DIM}" >&2
printf '%q ' python3 screen_cvs.py "${PY_ARGS[@]}" >&2
printf "${RESET}\n" >&2

python3 screen_cvs.py "${PY_ARGS[@]}"

printf "\n" >&2
ok "Done."
printf "${BOLD}${WHITE}Outputs:${RESET}\n" >&2
printf "  - %s\n" "$OUT_DIR/screening_results.csv" >&2
printf "  - %s\n" "$OUT_DIR/screening_results.xlsx" >&2
printf "  - %s\n" "$OUT_DIR/screening_report.md" >&2
printf "  - %s\n" "$OUT_DIR/passed_cvs/" >&2
printf "  - %s\n" "$OUT_DIR/failed_cvs/" >&2
printf "  - %s\n" "$OUT_DIR/ambiguous_cvs/" >&2
