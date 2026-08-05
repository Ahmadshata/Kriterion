#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Kriterion — Setup Script
# Installs everything needed to run the tool. Safe to run multiple times.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
AGENT_SOURCE="$SCRIPT_DIR/.github/agents/kriterion.agent.md"
SKILLS_SOURCE_DIR="$SCRIPT_DIR/.github/skills"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9

# ─── Styling ─────────────────────────────────────────────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]; then
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  RESET=$'\033[0m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  RED=$'\033[31m'
  CYAN=$'\033[36m'
else
  BOLD="" DIM="" RESET="" GREEN="" YELLOW="" RED="" CYAN=""
fi

ok()   { printf '  %b✔%b  %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '  %b⚠%b  %s\n' "$YELLOW" "$RESET" "$1"; }
err()  { printf '  %b✖%b  %s\n' "$RED" "$RESET" "$1" >&2; }
info() { printf '  %b→%b  %s\n' "$CYAN" "$RESET" "$1"; }
hr()   { printf '%b%*s%b\n' "$DIM" "${COLUMNS:-70}" "" "$RESET" | tr " " "─"; }

# ─── Gradient Rendering (from Heimdall) ─────────────────────────────────────
render_horizontal_gradient_line() {
  local line="$1"
  local animate="${2:-false}"
  local animation_delay="${3:-0.07}"
  local character=""
  local index=0
  local last=0
  local numerator=0
  local r=0 g=0 b=0

  while [[ "$line" == *" " ]]; do
    line="${line% }"
  done
  last=$((${#line} - 1))
  if ((last <= 0)); then
    printf '%s\n' "$line"
    return
  fi

  printf '%b' "$BOLD"
  for ((index = 0; index <= last; index++)); do
    character="${line:index:1}"
    # Gradient: orange (#f59e0b) → purple (#7c5cfc) → indigo (#4f46e5)
    if ((index * 2 <= last)); then
      numerator=$((index * 2))
      r=$((245 + (124 - 245) * numerator / last))
      g=$((158 + (92 - 158) * numerator / last))
      b=$((11 + (252 - 11) * numerator / last))
    else
      numerator=$((index * 2 - last))
      r=$((124 + (79 - 124) * numerator / last))
      g=$((92 + (70 - 92) * numerator / last))
      b=$((252 + (229 - 252) * numerator / last))
    fi
    printf '\033[38;2;%d;%d;%dm%s' "$r" "$g" "$b" "$character"
    if [[ "$animate" == "true" && "$character" != " " ]]; then
      sleep "$animation_delay"
    fi
  done
  printf '%b\n' "$RESET"
}

wordmark() {
  local figlet_output=""
  local line=""
  printf '\n'
  if [[ -t 1 && -z "${CI:-}" && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]; then
    if command -v figlet &>/dev/null; then
      if figlet_output="$(figlet "KRITERION" 2>/dev/null)"; then
        while IFS= read -r line; do
          render_horizontal_gradient_line "$line" true 0.005
        done <<<"$figlet_output"
        printf '%b  SETUP · CV SCREENING ENGINE%b\n' "$DIM" "$RESET"
        return
      fi
    fi
    # Fallback: spaced letters with gradient
    printf '  %b◈%b  ' "$BOLD$CYAN" "$RESET"
    render_horizontal_gradient_line "R E S U M E   T R I A G E" true
  else
    printf '  ◈  R E S U M E   T R I A G E\n'
  fi
  printf '%b     SETUP · CV SCREENING ENGINE%b\n' "$DIM" "$RESET"
}

# ─── Banner ──────────────────────────────────────────────────────────────────
wordmark
echo ""

# ─── 1. Check Python ─────────────────────────────────────────────────────────
hr
printf "${BOLD}  Checking Python...${RESET}\n"

PYTHON_CMD=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON_CMD="$cmd"
    break
  fi
done

if [[ -z "$PYTHON_CMD" ]]; then
  err "Python not found."
  echo ""
  echo "  Install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ from https://www.python.org/downloads/"
  echo "  or via your package manager:"
  echo ""
  echo "    macOS:   brew install python"
  echo "    Ubuntu:  sudo apt install python3 python3-venv"
  echo "    Fedora:  sudo dnf install python3"
  echo ""
  exit 1
fi

# Verify version
PYTHON_VERSION="$($PYTHON_CMD --version 2>&1 | awk '{print $2}')"
PYTHON_MAJOR="$(echo "$PYTHON_VERSION" | cut -d. -f1)"
PYTHON_MINOR="$(echo "$PYTHON_VERSION" | cut -d. -f2)"

if [[ "$PYTHON_MAJOR" -lt "$MIN_PYTHON_MAJOR" ]] || \
   { [[ "$PYTHON_MAJOR" -eq "$MIN_PYTHON_MAJOR" ]] && [[ "$PYTHON_MINOR" -lt "$MIN_PYTHON_MINOR" ]]; }; then
  err "Python ${PYTHON_VERSION} found, but ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required."
  echo ""
  echo "  Upgrade Python: https://www.python.org/downloads/"
  exit 1
fi

ok "Python ${PYTHON_VERSION} ($PYTHON_CMD)"

# ─── 2. Check venv module ────────────────────────────────────────────────────
if ! $PYTHON_CMD -m venv --help &>/dev/null; then
  err "Python venv module not available."
  echo ""
  echo "  Install it:"
  echo "    Ubuntu/Debian: sudo apt install python3-venv"
  echo "    Fedora:        sudo dnf install python3-libs"
  echo ""
  exit 1
fi

# ─── 3. Create virtual environment ──────────────────────────────────────────
hr
printf "${BOLD}  Virtual Environment...${RESET}\n"

if [[ -d "$VENV_DIR" ]]; then
  ok "Already exists at .venv/"
else
  info "Creating .venv/"
  $PYTHON_CMD -m venv "$VENV_DIR"
  ok "Created .venv/"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ─── 4. Upgrade pip ─────────────────────────────────────────────────────────
hr
printf "${BOLD}  Upgrading pip...${RESET}\n"

pip install --upgrade pip --quiet 2>/dev/null
ok "pip $(pip --version | awk '{print $2}')"

# ─── 5. Install dependencies ────────────────────────────────────────────────
hr
printf "${BOLD}  Installing dependencies...${RESET}\n"

if [[ ! -f "$REQUIREMENTS" ]]; then
  err "requirements.txt not found at: $REQUIREMENTS"
  exit 1
fi

pip install --quiet -r "$REQUIREMENTS"
ok "All packages installed"

# Show what was installed
echo ""
printf "${DIM}"
pip list --format=columns 2>/dev/null | grep -iE "pymupdf|python-docx|openpyxl|pyyaml|wheel" | while read -r line; do
  printf "     %s\n" "$line"
done
printf "${RESET}"

# ─── 6. Check optional OCR ──────────────────────────────────────────────────
hr
printf "${BOLD}  Optional: OCR support...${RESET}\n"

OCR_AVAILABLE=true
if ! pip show pytesseract &>/dev/null; then
  OCR_AVAILABLE=false
fi
if ! command -v tesseract &>/dev/null; then
  OCR_AVAILABLE=false
fi

if [[ "$OCR_AVAILABLE" == "true" ]]; then
  ok "OCR available (pytesseract + tesseract)"
else
  warn "OCR not installed (optional — only needed for scanned PDFs)"
  printf "${DIM}     To install later:\n"
  printf "       pip install pytesseract pillow\n"
  printf "       brew install tesseract  # macOS\n"
  printf "       sudo apt install tesseract-ocr  # Linux${RESET}\n"
fi

# ─── 7. Verify main script ──────────────────────────────────────────────────
hr
printf "${BOLD}  Checking tool files...${RESET}\n"

if [[ -f "$SCRIPT_DIR/kriterion.py" ]]; then
  ok "kriterion.py found"
else
  err "kriterion.py not found — is this the correct directory?"
  exit 1
fi

if [[ -f "$SCRIPT_DIR/kriterion.sh" ]]; then
  ok "kriterion.sh found"
  chmod +x "$SCRIPT_DIR/kriterion.sh"
else
  warn "kriterion.sh not found"
fi

chmod +x "$SCRIPT_DIR/setup.sh" 2>/dev/null || true

# ─── 8. Install AI agent and skills ─────────────────────────────────────────
hr
printf "${BOLD}  Installing AI agent and skills...${RESET}\n"

install_ai_files() {
  local tool_name="$1"
  local config_dir="$2"
  local agent_filename="$3"
  local skill_name=""
  local skill_source=""
  local skill_destination=""

  mkdir -p "$config_dir/agents"
  cp "$AGENT_SOURCE" "$config_dir/agents/$agent_filename"

  for skill_name in create-profile scan-cvs; do
    skill_source="$SKILLS_SOURCE_DIR/$skill_name/SKILL.md"
    skill_destination="$config_dir/skills/$skill_name"
    mkdir -p "$skill_destination"
    cp "$skill_source" "$skill_destination/SKILL.md"
  done

  ok "$tool_name agent and skills installed in ${config_dir/#$HOME/~}"
}

if [[ ! -f "$AGENT_SOURCE" ]]; then
  err "Kriterion agent not found at: $AGENT_SOURCE"
  exit 1
fi

for skill_name in create-profile scan-cvs; do
  if [[ ! -f "$SKILLS_SOURCE_DIR/$skill_name/SKILL.md" ]]; then
    err "Kriterion skill not found at: $SKILLS_SOURCE_DIR/$skill_name/SKILL.md"
    exit 1
  fi
done

install_ai_files "GitHub Copilot" "$HOME/.copilot" "kriterion.agent.md"
install_ai_files "Claude" "$HOME/.claude" "kriterion.md"

# ─── 9. Create cvs/ folder if missing ───────────────────────────────────────
if [[ ! -d "$SCRIPT_DIR/cvs" ]]; then
  mkdir -p "$SCRIPT_DIR/cvs"
  ok "Created cvs/ folder — place your CV files here"
else
  CV_COUNT=$(find "$SCRIPT_DIR/cvs" -maxdepth 1 \( -name "*.pdf" -o -name "*.docx" \) | wc -l | tr -d ' ')
  ok "cvs/ folder exists ($CV_COUNT files found)"
fi

# ─── 10. Check profile ──────────────────────────────────────────────────────
hr
printf "${BOLD}  Profile...${RESET}\n"

if [[ -f "$SCRIPT_DIR/profiles/profile.yaml" ]]; then
  ROLE="$(grep -m1 '^role:' "$SCRIPT_DIR/profiles/profile.yaml" | sed 's/^role:\s*//' | xargs)"
  ok "profiles/profile.yaml found (role: $ROLE)"
else
  warn "No profiles/profile.yaml — create one before running Kriterion"
  printf "${DIM}     See README.md for the profile format.${RESET}\n"
fi

# ─── Done ────────────────────────────────────────────────────────────────────
hr
echo ""
printf "${BOLD}${GREEN}  Setup complete!${RESET}\n"
echo ""
printf "  ${BOLD}To run the tool:${RESET}\n"
echo ""
printf "    ${CYAN}./kriterion.sh${RESET}\n"
echo ""
printf "  ${DIM}Place PDF/DOCX files in the cvs/ folder first.${RESET}\n"
printf "  ${DIM}Results will appear in a dated directory (e.g., Senior_DevOps_Engineer_2026-07-30/).${RESET}\n"
echo ""
hr
