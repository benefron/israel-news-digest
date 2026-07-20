#!/usr/bin/env bash
set -euo pipefail

LABEL="com.benefron.newsdigest"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
rm -f "$DEST"

echo "Uninstalled $LABEL (removed $DEST)"
