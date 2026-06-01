#!/usr/bin/env python3
"""
Generate a WeChat-friendly text summary of the day's trending report.

Reads the most recent data/trending_<date>.json and writes/prints a markdown
summary designed for WeChat delivery:
  - header with date and full HTML link
  - top 10 repos, each with: rank + name, ⭐/today, language, category,
    brief, advantages (bullets), link

Pure deterministic — no LLM, no network. Safe to call from cron.

Usage:
  python3 scripts/post_wechat_summary.py             # print to stdout
  python3 scripts/post_wechat_summary.py --emit      # print to stdout
                                                    # (cron harness sends final reply)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"

PAGES_URL = "https://gitgubjie.github.io/gh-trending-daily/"


def _md_escape(s: str) -> str:
    """Light escaping for WeChat — backticks, asterisks, pipes can confuse rendering."""
    if not s:
        return ""
    return s.replace("`", "'").replace("\n", " ").strip()


def _find_latest_trending() -> Path | None:
    files = sorted(DATA.glob("trending_*.json"), reverse=True)
    return files[0] if files else None


def _load_today() -> tuple[dict, str]:
    """Return (data_dict, iso_date_str). Falls back to the latest file."""
    p = _find_latest_trending()
    if not p:
        raise SystemExit("no data file found in data/")
    m = re.search(r"trending_(\d{4}-\d{2}-\d{2})\.json", p.name)
    date_str = m.group(1) if m else "unknown"
    return json.loads(p.read_text(encoding="utf-8")), date_str


def _format_number(n: int | float) -> str:
    if n is None:
        return "?"
    n = int(n)
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def _format_repo(rank: int, r: dict[str, Any]) -> str:
    name = r.get("full_name") or f"{r.get('owner','')}/{r.get('name','')}"
    url = r.get("url") or f"https://github.com/{name}"
    lang = r.get("language") or "—"
    stars = r.get("stars", 0)
    today = r.get("stars_today") or 0
    desc = _md_escape(r.get("description") or "")

    analysis = r.get("analysis") or {}
    brief = _md_escape(analysis.get("brief") or "")
    category = _md_escape(analysis.get("category") or "")
    advantages = analysis.get("advantages") or []
    scenarios = analysis.get("scenarios") or []

    lines = [f"**{rank}. {name}**  ⭐{_format_number(stars)}  +{_format_number(today)} today  `{lang}`"]
    if category:
        lines.append(f"分类：{category}")
    # Prefer analysis brief; fall back to repo description
    if brief and brief != _md_escape(r.get("description") or ""):
        lines.append(f"简介：{brief}")
    elif desc:
        lines.append(f"简介：{desc}")
    if advantages:
        adv_text = " · ".join(_md_escape(a) for a in advantages if a)
        if adv_text:
            lines.append(f"优势：{adv_text}")
    if scenarios:
        scen_text = " · ".join(_md_escape(s) for s in scenarios if s)
        if scen_text:
            lines.append(f"场景：{scen_text}")
    lines.append(url)
    return "\n".join(lines)


def build_summary(top_n: int = 10) -> str:
    data, date_str = _load_today()
    repos = data.get("repos") or []
    if not repos:
        return f"⚠️ GitHub Trending · {date_str}\n今日未抓到数据，链接：{PAGES_URL}"

    top = repos[:top_n]
    header = f"🔥 **GitHub 今日热门 Top {len(top)}** · {date_str}\n完整报告（精选 + AI 分析）：{PAGES_URL}\n"
    body = "\n\n".join(_format_repo(i + 1, r) for i, r in enumerate(top))
    footer = f"\n\n— 共 {len(repos)} 个 trending 项目已收录到日报。"
    return header + "\n\n" + body + footer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--emit", action="store_true",
                    help="(no-op flag for cron harness compatibility)")
    args = ap.parse_args()
    print(build_summary(top_n=args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
