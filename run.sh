#!/usr/bin/env bash
# End-to-end run: fetch → analyze → render → publish → wechat summary.
# Usage: ./run.sh [--no-publish] [--no-summary]
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ [1/4] fetch trending"
python3 scripts/fetch_trending.py

echo "▶ [2/4] render html (with AI analysis)"
python3 scripts/render_html.py

if [[ "${1:-}" != "--no-publish" ]] && [[ "${2:-}" != "--no-summary" ]]; then
  echo "▶ [3/4] publish to github pages"
  python3 scripts/publish.py
fi

if [[ "${2:-}" != "--no-summary" ]]; then
  echo "▶ [4/4] generate wechat summary"
  python3 scripts/post_wechat_summary.py
fi

echo "✓ done"
