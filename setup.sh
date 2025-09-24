#!/usr/bin/env bash
# QMB6Pro – one-shot setup for Linux/macOS
# Tworzy .venv, instaluje zależności z requirements.txt i (opcjonalnie) odpala app_gui.py
# Użycie:
#   bash setup.sh           # tylko instalacja
#   bash setup.sh --run     # instalacja + start GUI
#   bash setup.sh --rebuild # czyści .venv i instaluje od zera

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PY_BIN=""
choose_python() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY_BIN="$c"; return; fi
  done
  echo "No Python found. Install Python 3 first." >&2
  exit 1
}

need_system_hints() {
  echo "Heads-up: if install blows up on Tk/matplotlib, do system deps once:"
  if command -v apt >/dev/null 2>&1 || command -v apt-get >/dev/null 2>&1; then
    echo "  sudo apt-get update && sudo apt-get install -y python3-tk tk libfreetype6-dev pkg-config"
  elif command -v dnf >/dev/null 2>&1; then
    echo "  sudo dnf install -y python3-tkinter freetype-devel pkgconf-pkg-config"
  elif command -v pacman >/dev/null 2>&1; then
    echo "  sudo pacman -S --needed tk freetype2"
  else
    echo "  Install your distro’s Tk + freetype dev packages if needed."
  fi
}

rebuild=0
run_after=0
for a in "$@"; do
  case "$a" in
    --run) run_after=1 ;;
    --rebuild) rebuild=1 ;;
    *) echo "Unknown arg: $a" >&2; exit 2 ;;
  esac
done

choose_python

if [ $rebuild -eq 1 ] && [ -d ".venv" ]; then
  echo "[*] Removing existing .venv"
  rm -rf .venv
fi

if [ ! -d ".venv" ]; then
  echo "[*] Creating virtualenv (.venv)"
  "$PY_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[*] Upgrading pip"
python -m pip install --upgrade pip wheel setuptools

echo "[*] Installing project requirements"
if [ ! -f requirements.txt ]; then
  echo "requirements.txt missing. You’re in the wrong folder, Sherlock." >&2
  exit 1
fi

# pro tip: pypi czasem zdycha, spróbuj jeszcze raz po niepowodzeniu
pip install -r requirements.txt || { need_system_hints; echo "Retrying pip after hints..."; pip install -r requirements.txt; }

# sanity check imports
echo "[*] Verifying imports"
python - <<'PY'
mods = ["ttkbootstrap","matplotlib","serial","minimalmodbus","tkinter"]
failed = []
for m in mods:
    try:
        __import__(m)
    except Exception as e:
        failed.append((m, str(e)))
if failed:
    import sys
    print("Import check failed for:", failed, file=sys.stderr)
    sys.exit(1)
print("All good.")
PY

echo
echo "[✓] Environment ready."
echo "   To use later:  source .venv/bin/activate"
echo "   Run app:       python app_gui.py"
echo

if [ $run_after -eq 1 ]; then
  echo "[*] Launching GUI…"
  exec python app_gui.py
fi
#