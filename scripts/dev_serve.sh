#!/usr/bin/env bash
# Stages site/ + data/latest.json into the exact same relative layout the
# production Pages deploy uses (see .github/workflows/deploy-pages.yml),
# then serves it locally, so local dev never diverges from prod paths.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="$REPO_ROOT/_dev"
PORT="${1:-8080}"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/data"
cp -R "$REPO_ROOT/site/." "$STAGE_DIR/"
cp "$REPO_ROOT/data/latest.json" "$STAGE_DIR/data/latest.json"
cp "$REPO_ROOT/data/preferences.json" "$STAGE_DIR/data/preferences.json"
cp "$REPO_ROOT/data/topic_catalog.json" "$STAGE_DIR/data/topic_catalog.json"

echo "Serving $STAGE_DIR at http://localhost:$PORT"
cd "$STAGE_DIR"
python3 -m http.server "$PORT"
