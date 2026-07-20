#!/usr/bin/env bash
# Installs the daily LaunchAgent: runs automation/run_daily.py at 07:00,
# 12:00, 15:00, and 19:00, catching up on the next wake if the Mac was
# asleep/off at any of those times (see the .plist.template for why
# RunAtLoad is deliberately not used).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.benefron.newsdigest"
TEMPLATE="$REPO_ROOT/scripts/$LABEL.plist.template"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "== preflight =="

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
  echo "WARNING: 'claude' not found on PATH. The pipeline will use the GitHub Copilot API fallback for summarisation. Install Claude Code CLI if you want the primary Claude path." >&2
  CLAUDE_BIN_DIR="/usr/local/bin"  # placeholder; gh is at /opt/homebrew/bin which is already in PATH
else
  CLAUDE_BIN_DIR="$(dirname "$CLAUDE_BIN")"
  echo "claude: $CLAUDE_BIN"
fi

if [ ! -x "$REPO_ROOT/automation/.venv/bin/python3" ]; then
  echo "ERROR: automation/.venv not found. Run:" >&2
  echo "  cd $REPO_ROOT && python3 -m venv automation/.venv && automation/.venv/bin/pip install -r automation/requirements.txt" >&2
  exit 1
fi
echo "venv: OK"

if [ ! -f "$REPO_ROOT/automation/secrets.local.json" ]; then
  echo "WARNING: automation/secrets.local.json not found — Gmail preference sync will have no sender allowlist configured."
fi

if ! git -C "$REPO_ROOT" remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: no 'origin' git remote configured in $REPO_ROOT" >&2
  exit 1
fi
CRED_HELPER="$(git -C "$REPO_ROOT" config --get credential.helper || true)"
if [ "$CRED_HELPER" != "osxkeychain" ]; then
  echo "WARNING: git credential.helper is '$CRED_HELPER', not 'osxkeychain' — non-interactive push from launchd may prompt/fail."
else
  echo "git push credentials: osxkeychain (OK for non-interactive push)"
fi

echo "== installing =="

mkdir -p "$REPO_ROOT/automation/logs" "$REPO_ROOT/automation/state"

sed -e "s#__REPO_ROOT__#$REPO_ROOT#g" -e "s#__CLAUDE_BIN_DIR__#$CLAUDE_BIN_DIR#g" \
  "$TEMPLATE" > "$DEST"

mkdir -p "$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl enable "gui/$UID_NUM/$LABEL"

echo "== done =="
launchctl list | grep "$LABEL" || echo "(not showing in launchctl list yet — it only appears once scheduled to run)"
echo "Installed: $DEST"
echo "Logs: $REPO_ROOT/automation/logs/launchd.{out,err}.log"
echo "Scheduled: 07:00 / 10:00 / 12:00 / 15:00 / 17:00 / 19:00 / 21:00 daily (or next wake if missed)"
echo "Manual test run: $REPO_ROOT/scripts/run_now.sh"
