#!/usr/bin/env bash
# End-to-end run: fetch → render → publish.
# Usage: ./run.sh [--no-publish]
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ fetch trending"
python3 scripts/fetch_trending.py

echo "▶ render html"
python3 scripts/render_html.py

if [[ "${1:-}" != "--no-publish" ]]; then
  echo "▶ publish to github pages"
  python3 scripts/publish.py
fi

echo "✓ done"
