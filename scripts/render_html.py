#!/usr/bin/env python3
"""
Render trending JSON into a polished, self-contained HTML report.

Design principles:
  - dark theme by default, light theme auto-switched by prefers-color-scheme
  - zero external assets (no CDN, no fonts) — works offline, works on Pages
  - responsive (mobile + desktop), accessible, fast (<30KB gzipped target)
  - one index.html for the current day; archive sub-pages by date
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# --- HTML template (Jinja2) ---
HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="gh-trending-daily">
<meta name="description" content="GitHub 每日热门项目报告 · {{ date }}">
<title>GitHub Trending · {{ date }}</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #0d1117;
    --bg-elev: #161b22;
    --bg-card: #1c2129;
    --border: #30363d;
    --border-soft: #21262d;
    --fg: #e6edf3;
    --fg-muted: #8b949e;
    --fg-dim: #6e7681;
    --accent: #58a6ff;
    --accent-2: #7ee787;
    --warn: #f0883e;
    --star: #e3b341;
    --shadow: 0 1px 0 rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.18);
    --radius: 10px;
    --radius-sm: 6px;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #ffffff;
      --bg-elev: #f6f8fa;
      --bg-card: #ffffff;
      --border: #d0d7de;
      --border-soft: #eaeef2;
      --fg: #1f2328;
      --fg-muted: #59636e;
      --fg-dim: #818b98;
      --accent: #0969da;
      --accent-2: #1a7f37;
      --warn: #bc4c00;
      --star: #bf8700;
      --shadow: 0 1px 0 rgba(31,35,40,.04), 0 8px 24px rgba(31,35,40,.08);
    }
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--fg);
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
          "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }

  .wrap { max-width: 920px; margin: 0 auto; padding: 32px 20px 80px; }

  /* Header */
  .hdr { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .hdr h1 { font-size: 28px; margin: 0; letter-spacing: -.01em; }
  .hdr .date { color: var(--fg-muted); font-family: var(--mono); font-size: 14px; }
  .hdr .count {
    margin-left: auto;
    color: var(--fg-muted);
    font-size: 13px;
  }
  .hdr .count b { color: var(--fg); font-weight: 600; }

  .lede {
    color: var(--fg-muted);
    margin: 8px 0 28px;
    font-size: 14px;
  }
  .lede a { color: var(--fg-muted); border-bottom: 1px dotted var(--fg-muted); }
  .lede a:hover { color: var(--accent); border-color: var(--accent); text-decoration: none; }

  /* Stats strip */
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin: 0 0 24px;
  }
  .stat {
    background: var(--bg-elev);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
  }
  .stat .k { color: var(--fg-dim); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
  .stat .v { font-family: var(--mono); font-size: 16px; margin-top: 2px; color: var(--fg); }
  @media (max-width: 600px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
  }

  /* Repo list */
  ol.repos { list-style: none; padding: 0; margin: 0; counter-reset: r; }
  .repo {
    counter-increment: r;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 18px 16px;
    margin: 0 0 12px;
    box-shadow: var(--shadow);
    transition: transform .08s ease, border-color .15s ease;
  }
  .repo:hover { border-color: var(--fg-dim); }
  .repo-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .repo-num {
    color: var(--fg-dim);
    font-family: var(--mono);
    font-size: 13px;
    min-width: 28px;
  }
  .repo-num::before { content: counter(r, decimal-leading-zero); }
  .repo-owner { color: var(--fg-muted); font-weight: 400; }
  .repo-name { color: var(--accent); font-weight: 600; }
  .repo-name:hover { text-decoration: underline; }
  .repo-desc {
    color: var(--fg);
    margin: 8px 0 10px 36px;
    font-size: 14px;
    line-height: 1.5;
  }
  .repo-desc:empty { display: none; }
  .repo-meta {
    display: flex; align-items: center; flex-wrap: wrap; gap: 16px;
    color: var(--fg-muted);
    font-size: 13px;
    margin-left: 36px;
  }
  .repo-meta .item { display: inline-flex; align-items: center; gap: 4px; }
  .repo-meta .lang-dot {
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    border: 1px solid rgba(255,255,255,.1);
  }
  .repo-meta .today {
    color: var(--star);
    font-weight: 600;
  }
  .repo-meta .today::before { content: "★ "; }

  /* Footer */
  .ftr {
    margin-top: 36px;
    padding-top: 16px;
    border-top: 1px solid var(--border-soft);
    color: var(--fg-dim);
    font-size: 12px;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  }
  .ftr code { font-family: var(--mono); font-size: 11px; }

  @media (max-width: 600px) {
    .wrap { padding: 20px 14px 60px; }
    .hdr h1 { font-size: 22px; }
    .repo { padding: 14px; }
    .repo-desc, .repo-meta { margin-left: 0; }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>GitHub Trending</h1>
    <span class="date">{{ date }}</span>
    <span class="count"><b>{{ count }}</b> repos trending today</span>
  </div>
  <p class="lede">
    Daily snapshot of <a href="https://github.com/trending?since=daily" rel="noopener">github.com/trending?since=daily</a>.
    Ranked by stars gained in the last 24 hours.
  </p>

  <div class="stats">
    <div class="stat"><div class="k">Top language</div><div class="v">{{ top_lang }}</div></div>
    <div class="stat"><div class="k">Total stars today</div><div class="v">{{ '{:,}'.format(total_today) }}</div></div>
    <div class="stat"><div class="k">Total stars</div><div class="v">{{ '{:,}'.format(total_stars) }}</div></div>
    <div class="stat"><div class="k">Avg today</div><div class="v">{{ '{:,}'.format(avg_today) }}</div></div>
  </div>

  <ol class="repos">
    {%- for r in repos %}
    <li class="repo">
      <div class="repo-row">
        <span class="repo-num"></span>
        <span class="repo-owner">{{ r.owner }}/</span>
        <a class="repo-name" href="{{ r.url }}" rel="noopener">{{ r.name }}</a>
      </div>
      {%- if r.description %}
      <p class="repo-desc">{{ r.description }}</p>
      {%- endif %}
      <div class="repo-meta">
        {%- if r.language %}
        <span class="item" title="{{ r.language }}">
          <span class="lang-dot" style="background:{{ r.language_color }}"></span>
          {{ r.language }}
        </span>
        {%- endif %}
        <span class="item">{{ r.stars_fmt }} stars</span>
        <span class="item">{{ r.forks_fmt }} forks</span>
        <span class="item today">{{ r.stars_today_fmt }} today</span>
      </div>
    </li>
    {%- endfor %}
  </ol>

  <div class="ftr">
    <span>generated {{ generated_at }} · <code>gh-trending-daily</code></span>
    <span><a href="./archive.html">archive →</a></span>
  </div>
</div>
</body>
</html>
"""

# --- Archive page template ---
ARCHIVE_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Archive · GitHub Trending</title>
<style>
  :root { color-scheme: light dark; --bg:#0d1117; --fg:#e6edf3; --muted:#8b949e; --border:#30363d; --card:#161b22; }
  @media (prefers-color-scheme: light) { :root { --bg:#fff; --fg:#1f2328; --muted:#59636e; --border:#d0d7de; --card:#f6f8fa; } }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
  .wrap{max-width:920px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:24px;margin:0 0 8px}
  p{color:var(--muted);margin:0 0 24px}
  ul{list-style:none;padding:0;margin:0}
  li{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--card);border:1px solid var(--border);border-radius:6px;margin-bottom:8px}
  li a{color:var(--fg);font-weight:600}
  li a:hover{color:#58a6ff}
  .meta{color:var(--muted);font-family:ui-monospace,Consolas,monospace;font-size:13px}
</style>
</head>
<body>
<div class="wrap">
  <h1>Archive</h1>
  <p>Past trending reports, newest first.</p>
  <ul>
    {%- for d in days %}
    <li>
      <a href="./reports/{{ d.date }}.html">{{ d.date }}</a>
      <span class="meta">{{ d.count }} repos · {{ d.total_today_fmt }} ★ today</span>
    </li>
    {%- endfor %}
  </ul>
  <p style="margin-top:32px"><a href="./index.html">← back to today</a></p>
</div>
</html>
"""


def _fmt(n: int) -> str:
    return f"{n:,}"


def render(payload: dict) -> str:
    """Render a single-day report. Returns full HTML string."""
    from jinja2 import Environment, select_autoescape
    env = Environment(autoescape=select_autoescape(["html"]))
    tpl = env.from_string(HTML_TEMPLATE)
    repos = payload["repos"]
    # pre-format numbers (Jinja2's '{,}'.format gets parsed as placeholder)
    for r in repos:
        r["stars_fmt"] = _fmt(r["stars"])
        r["forks_fmt"] = _fmt(r["forks"])
        r["stars_today_fmt"] = _fmt(r["stars_today"])
    # quick stats
    langs = [r["language"] for r in repos if r["language"]]
    top_lang = max(set(langs), key=langs.count) if langs else "—"
    total_today = sum(r["stars_today"] for r in repos)
    total_stars = sum(r["stars"] for r in repos)
    avg_today = round(total_today / len(repos)) if repos else 0
    return tpl.render(
        date=payload["date"],
        count=payload["count"],
        repos=repos,
        top_lang=top_lang,
        total_today=total_today,
        total_stars=total_stars,
        avg_today=avg_today,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
    )


def render_archive(days: list[dict]) -> str:
    from jinja2 import Environment, select_autoescape
    env = Environment(autoescape=select_autoescape(["html"]))
    return env.from_string(ARCHIVE_TEMPLATE).render(days=days)


def main() -> int:
    base = Path(__file__).resolve().parent.parent
    data_dir = base / "data"
    site_dir = base / "site"
    site_dir.mkdir(exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)

    # find the latest data file (today's)
    files = sorted(data_dir.glob("trending_*.json"))
    if not files:
        print("[error] no data files found in", data_dir, file=sys.stderr)
        return 1
    today_file = files[-1]
    payload = json.loads(today_file.read_text())

    # 1. render today's index.html
    (site_dir / "index.html").write_text(render(payload), encoding="utf-8")
    print(f"[write] site/index.html")

    # 2. archive this day under reports/<date>.html
    (site_dir / "reports" / f"{payload['date']}.html").write_text(
        render(payload), encoding="utf-8"
    )
    print(f"[write] site/reports/{payload['date']}.html")

    # 3. rebuild archive.html from all data files
    days = []
    for f in files:
        p = json.loads(f.read_text())
        total_today = sum(r["stars_today"] for r in p["repos"])
        days.append({
            "date": p["date"],
            "count": p["count"],
            "total_today": total_today,
            "total_today_fmt": _fmt(total_today),
        })
    days.reverse()  # newest first
    (site_dir / "archive.html").write_text(render_archive(days), encoding="utf-8")
    print(f"[write] site/archive.html ({len(days)} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
