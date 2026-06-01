#!/usr/bin/env python3
"""
Render trending JSON into a polished, self-contained HTML report.

设计：
  - 暗色为默认主题，浅色随系统自动切换（prefers-color-scheme）
  - 零外部资源（无 CDN、无字体），离线可用
  - 响应式、移动友好；< 30KB gzip
  - 每个 repo 都有 AI 分析（brief / 优势 / 场景 / 分类）
  - 首页 index.html 当天报告；archive.html 历史索引；reports/<date>.html 历史单日报告
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# --- 主页模板 ---
HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="gh-trending-daily">
<meta name="description" content="GitHub 每日热门项目精选报告 · {{ date }}，附 AI 分析核心优势与适用场景。">
<title>GitHub 热门项目日报 · {{ date }}</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #0d1117;
    --bg-elev: #161b22;
    --bg-card: #1c2129;
    --bg-soft: #20262d;
    --border: #30363d;
    --border-soft: #21262d;
    --fg: #e6edf3;
    --fg-muted: #8b949e;
    --fg-dim: #6e7681;
    --accent: #58a6ff;
    --accent-2: #7ee787;
    --accent-3: #d2a8ff;
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
      --bg-soft: #f3f5f8;
      --border: #d0d7de;
      --border-soft: #eaeef2;
      --fg: #1f2328;
      --fg-muted: #59636e;
      --fg-dim: #818b98;
      --accent: #0969da;
      --accent-2: #1a7f37;
      --accent-3: #8250df;
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
  .hdr h1 .badge {
    display: inline-block; font-size: 11px; font-weight: 600;
    padding: 2px 8px; margin-left: 6px; border-radius: 99px;
    background: var(--accent-2); color: #0d1117; vertical-align: middle;
    letter-spacing: .04em; text-transform: uppercase;
  }
  .hdr .date { color: var(--fg-muted); font-family: var(--mono); font-size: 14px; }
  .hdr .count { margin-left: auto; color: var(--fg-muted); font-size: 13px; }
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
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 8px; margin: 0 0 24px;
  }
  .stat {
    background: var(--bg-elev); border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm); padding: 10px 12px;
  }
  .stat .k { color: var(--fg-dim); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
  .stat .v { font-family: var(--mono); font-size: 16px; margin-top: 2px; color: var(--fg); }

  /* Category tags */
  .cats { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 24px; }
  .cat {
    font-size: 12px; padding: 3px 9px; border-radius: 99px;
    background: var(--bg-soft); color: var(--fg-muted);
    border: 1px solid var(--border-soft);
  }
  .cat b { color: var(--fg); font-weight: 600; }

  /* Repo list */
  ol.repos { list-style: none; padding: 0; margin: 0; counter-reset: r; }
  .repo {
    counter-increment: r;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 18px 16px;
    margin: 0 0 14px;
    box-shadow: var(--shadow);
    transition: border-color .15s ease;
  }
  .repo:hover { border-color: var(--fg-dim); }
  .repo-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .repo-num {
    color: var(--fg-dim); font-family: var(--mono); font-size: 13px; min-width: 28px;
  }
  .repo-num::before { content: counter(r, decimal-leading-zero); }
  .repo-owner { color: var(--fg-muted); font-weight: 400; font-family: var(--mono); font-size: 14px; }
  .repo-name { color: var(--accent); font-weight: 600; font-family: var(--mono); font-size: 15px; }
  .repo-name:hover { text-decoration: underline; }
  .repo-cat {
    margin-left: auto;
    font-size: 11px; padding: 2px 8px; border-radius: 99px;
    background: rgba(125, 87, 255, 0.12); color: var(--accent-3);
    border: 1px solid rgba(125, 87, 255, 0.3);
    font-weight: 500;
  }

  .repo-brief {
    color: var(--fg);
    margin: 10px 0 12px 36px;
    font-size: 14.5px; line-height: 1.5;
  }
  .repo-brief:empty { display: none; }

  /* AI 分析区 */
  .analysis {
    margin: 0 0 12px 36px;
    padding: 12px 14px;
    background: var(--bg-soft);
    border-left: 3px solid var(--accent-3);
    border-radius: var(--radius-sm);
    font-size: 13.5px;
  }
  .analysis:empty { display: none; }
  .analysis h4 {
    margin: 0 0 8px;
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .08em;
    color: var(--accent-3);
  }
  .analysis .advantages,
  .analysis .scenarios {
    display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px;
  }
  .analysis .advantages { list-style: none; padding: 0; }
  .analysis .tag {
    display: inline-block; padding: 3px 9px; border-radius: 99px;
    background: var(--bg-card); border: 1px solid var(--border);
    color: var(--fg); font-size: 12.5px;
  }
  .analysis .tag.adv { color: var(--accent-2); border-color: rgba(126, 231, 135, 0.3); }
  .analysis .tag.scen { color: var(--warn); border-color: rgba(240, 136, 62, 0.3); }
  .analysis p { margin: 4px 0; color: var(--fg-muted); font-size: 13px; }

  .repo-meta {
    display: flex; align-items: center; flex-wrap: wrap; gap: 14px;
    color: var(--fg-muted); font-size: 13px; margin-left: 36px;
  }
  .repo-meta .item { display: inline-flex; align-items: center; gap: 4px; }
  .repo-meta .lang-dot {
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    border: 1px solid rgba(255,255,255,.15);
  }
  .repo-meta .today {
    color: var(--star); font-weight: 600;
  }
  .repo-meta .today::before { content: "★ "; }

  /* Footer */
  .ftr {
    margin-top: 36px; padding-top: 16px;
    border-top: 1px solid var(--border-soft);
    color: var(--fg-dim); font-size: 12px;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  }
  .ftr code { font-family: var(--mono); font-size: 11px; }

  @media (max-width: 600px) {
    .wrap { padding: 20px 14px 60px; }
    .hdr h1 { font-size: 22px; }
    .stats { grid-template-columns: repeat(2, 1fr); }
    .repo { padding: 14px; }
    .repo-brief, .analysis, .repo-meta { margin-left: 0; }
    .repo-cat { margin-left: 0; }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>GitHub 热门项目日报<span class="badge">DAILY</span></h1>
    <span class="date">{{ date }}</span>
    <span class="count"><b>{{ count }}</b> 个项目正在飙升</span>
  </div>
  <p class="lede">
    抓取自 <a href="https://github.com/trending?since=daily" rel="noopener">github.com/trending?since=daily</a>，
    按过去 24 小时新增 star 数排序。每个项目都附带 AI 总结的核心优势与适用场景。
  </p>

  <div class="stats">
    <div class="stat"><div class="k">主语言</div><div class="v">{{ top_lang }}</div></div>
    <div class="stat"><div class="k">今日新增 ★</div><div class="v">{{ total_today_fmt }}</div></div>
    <div class="stat"><div class="k">总 star 数</div><div class="v">{{ total_stars_fmt }}</div></div>
    <div class="stat"><div class="k">均值 / 项目</div><div class="v">{{ avg_today_fmt }}</div></div>
  </div>

  {%- if category_summary %}
  <div class="cats">
    {%- for cat, n in category_summary %}
    <span class="cat"><b>{{ n }}</b> {{ cat }}</span>
    {%- endfor %}
  </div>
  {%- endif %}

  <ol class="repos">
    {%- for r in repos %}
    <li class="repo">
      <div class="repo-row">
        <span class="repo-num"></span>
        <span class="repo-owner">{{ r.owner }}/</span>
        <a class="repo-name" href="{{ r.url }}" rel="noopener">{{ r.name }}</a>
        {%- if r.analysis and r.analysis.category %}
        <span class="repo-cat">{{ r.analysis.category }}</span>
        {%- endif %}
      </div>
      {%- if r.analysis and r.analysis.brief %}
      <p class="repo-brief">{{ r.analysis.brief }}</p>
      {%- endif %}
      {%- set a = r.analysis or {} %}
      {%- if a.advantages or a.scenarios %}
      <div class="analysis">
        <h4>✦ AI 核心优势分析</h4>
        {%- if a.advantages %}
        <ul class="advantages">
          {%- for adv in a.advantages %}
          <li><span class="tag adv">{{ adv }}</span></li>
          {%- endfor %}
        </ul>
        {%- endif %}
        {%- if a.scenarios %}
        <p><b style="color:var(--fg);">典型场景：</b></p>
        <div class="scenarios">
          {%- for s in a.scenarios %}
          <span class="tag scen">{{ s }}</span>
          {%- endfor %}
        </div>
        {%- endif %}
      </div>
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
    <span>生成于 {{ generated_at }} · <code>gh-trending-daily</code></span>
    <span><a href="./archive.html">往期归档 →</a></span>
  </div>
</div>
</body>
</html>
"""

# --- 归档页模板 ---
ARCHIVE_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>归档 · GitHub 热门项目日报</title>
<style>
  :root { color-scheme: light dark; --bg:#0d1117; --fg:#e6edf3; --muted:#8b949e; --border:#30363d; --card:#161b22; --accent:#58a6ff; }
  @media (prefers-color-scheme: light) { :root { --bg:#fff; --fg:#1f2328; --muted:#59636e; --border:#d0d7de; --card:#f6f8fa; --accent:#0969da; } }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
  .wrap{max-width:920px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:24px;margin:0 0 8px}
  p{color:var(--muted);margin:0 0 24px}
  ul{list-style:none;padding:0;margin:0}
  li{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--card);border:1px solid var(--border);border-radius:6px;margin-bottom:8px}
  li a{color:var(--fg);font-weight:600}
  li a:hover{color:var(--accent);text-decoration:none}
  .meta{color:var(--muted);font-family:ui-monospace,Consolas,monospace;font-size:13px}
</style>
</head>
<body>
<div class="wrap">
  <h1>归档</h1>
  <p>历史报告索引，最新在前。点击查看当日完整分析。</p>
  <ul>
    {%- for d in days %}
    <li>
      <a href="./reports/{{ d.date }}.html">{{ d.date }}</a>
      <span class="meta">{{ d.count }} 项目 · {{ d.total_today_fmt }} ★ today</span>
    </li>
    {%- endfor %}
  </ul>
  <p style="margin-top:32px"><a href="./index.html">← 回到今天</a></p>
</div>
</html>
"""


def _fmt(n: int) -> str:
    return f"{n:,}"


def _build_category_summary(repos: list[dict]) -> list[tuple[str, int]]:
    """统计分类（按数量降序，filter 掉"其他"如果非首位）。"""
    cats = [r.get("analysis", {}).get("category", "其他") for r in repos]
    counter = Counter(cats)
    # 排序：出现次数降序；过滤掉"其他"（除非只有它）
    items = sorted(counter.items(), key=lambda x: -x[1])
    items = [(k, v) for k, v in items if k != "其他"] or [("其他", len(repos))]
    return items


def render_day(payload: dict) -> str:
    """渲染单日报告。"""
    from jinja2 import Environment, select_autoescape
    env = Environment(autoescape=select_autoescape(["html"]))
    tpl = env.from_string(HTML_TEMPLATE)
    repos = payload["repos"]
    for r in repos:
        r["stars_fmt"] = _fmt(r["stars"])
        r["forks_fmt"] = _fmt(r["forks"])
        r["stars_today_fmt"] = _fmt(r["stars_today"])
    langs = [r["language"] for r in repos if r.get("language")]
    top_lang = max(set(langs), key=langs.count) if langs else "—"
    total_today = sum(r["stars_today"] for r in repos)
    total_stars = sum(r["stars"] for r in repos)
    avg_today = round(total_today / len(repos)) if repos else 0
    return tpl.render(
        date=payload["date"],
        count=payload["count"],
        repos=repos,
        top_lang=top_lang,
        total_today=total_today, total_today_fmt=_fmt(total_today),
        total_stars=total_stars, total_stars_fmt=_fmt(total_stars),
        avg_today=avg_today, avg_today_fmt=_fmt(avg_today),
        category_summary=_build_category_summary(repos),
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

    files = sorted(data_dir.glob("trending_*.json"))
    if not files:
        print("[error] no data files found in", data_dir, file=sys.stderr)
        return 1

    # AI 分析（只对当日数据做，历史数据如果没 analysis 也跳过）
    try:
        from analyze import analyze_repos
    except ImportError:
        analyze_repos = None

    today_file = files[-1]
    payload = json.loads(today_file.read_text())
    if analyze_repos and not payload["repos"][0].get("analysis"):
        analyze_repos(payload["repos"])
        # 写回 json，下次直接复用
        today_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    # 当日 index.html
    (site_dir / "index.html").write_text(render_day(payload), encoding="utf-8")
    print(f"[write] site/index.html")

    # 当日归档副本
    (site_dir / "reports" / f"{payload['date']}.html").write_text(
        render_day(payload), encoding="utf-8"
    )
    print(f"[write] site/reports/{payload['date']}.html")

    # 重建 archive.html
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
    days.reverse()
    (site_dir / "archive.html").write_text(render_archive(days), encoding="utf-8")
    print(f"[write] site/archive.html ({len(days)} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
