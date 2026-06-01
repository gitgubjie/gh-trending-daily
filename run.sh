#!/usr/bin/env bash
# End-to-end run: fetch → analyze → render → publish.
# Usage: ./run.sh [--no-publish]
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ [1/3] fetch trending"
python3 scripts/fetch_trending.py

echo "▶ [2/3] render html (with AI analysis)"
python3 scripts/render_html.py

if [[ "${1:-}" != "--no-publish" ]]; then
  echo "▶ [3/3] publish to github pages"
  python3 scripts/publish.py
fi

echo "✓ done"
