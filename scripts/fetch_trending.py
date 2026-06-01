#!/usr/bin/env python3
"""
Fetch GitHub Trending repositories (daily) and save as JSON.

GitHub Trending page is server-rendered HTML; we parse it with BeautifulSoup
to extract repo metadata. We also enrich each repo with language color, star
count, fork count, and a one-line description via the GitHub REST API
(optional, requires GITHUB_TOKEN to bump rate limit from 60 to 5000/hr).

Output: data/trending_YYYY-MM-DD.json
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --- Config ---
TRENDING_URL = "https://github.com/trending?since=daily"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 30
RETRY = 3
SLEEP = 1.5  # polite delay between API calls

# --- Language colors (subset; full list in assets/lang-colors.json if needed) ---
LANG_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "C++": "#f34b7d",
    "C": "#555555",
    "Java": "#b07219",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "C#": "#178600",
    "Shell": "#89e051",
    "Dart": "#00B4AB",
    "Lua": "#000080",
    "Scala": "#c22d40",
    "Elixir": "#6e4a7e",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Vue": "#41b883",
    "Jupyter Notebook": "#DA5B0B",
    "Solidity": "#AA6746",
    "Zig": "#ec915c",
    "Move": "#4a1378",
    "MDX": "#fcb32c",
}


def fetch_trending_html() -> str:
    last_err = None
    for attempt in range(1, RETRY + 1):
        try:
            r = requests.get(TRENDING_URL, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            last_err = e
            print(f"  fetch attempt {attempt} failed: {e}", file=sys.stderr)
            time.sleep(2 * attempt)
    raise RuntimeError(f"failed to fetch trending page: {last_err}")


def parse_trending(html: str) -> list[dict]:
    """Parse the GitHub Trending HTML into a list of repo dicts.

    The trending page structure (as of 2024-2025) is:
      <article class="Box-row">
        <h2><a href="/owner/repo">owner / repo</a></h2>
        <p class="col-9 ...">description</p>
        <div class="f6 ...">
          <span>language</span>
          <a href="/owner/repo/stargazers">N</a>
          <a href="/owner/repo/network/members">N</a>
        </div>
      </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.Box-row")
    repos = []
    for art in articles:
        h2 = art.select_one("h2 a")
        if not h2:
            continue
        href = h2.get("href", "").strip("/")
        owner, _, name = href.partition("/")
        if not owner or not name:
            continue

        # description (may be empty)
        desc_tag = art.select_one("p.col-9, p.color-fg-muted")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # language
        lang_tag = art.select_one(
            "span[itemprop='programmingLanguage'], "
            "span.d-inline-block[class*='color-fg-default']"
        )
        language = lang_tag.get_text(strip=True) if lang_tag else ""
        # fallback: look for color span next to language
        if not language:
            lang_color_span = art.select_one("span.repo-language-color")
            if lang_color_span and lang_color_span.parent:
                language = lang_color_span.parent.get_text(strip=True)

        # star / fork counts (look for the icons in the f6 row)
        stars = 0
        forks = 0
        for a in art.select("a.Link--muted"):
            text = a.get_text(strip=True).replace(",", "")
            if text.isdigit():
                href_a = a.get("href", "")
                if "/stargazers" in href_a:
                    stars = int(text)
                elif "/network/members" in href_a or "/forks" in href_a:
                    forks = int(text)

        # today's stars: usually only on top of "stars today" section
        # find the first span containing "stars today"
        stars_today = 0
        for span in art.select("span"):
            t = span.get_text(strip=True)
            m = re.search(r"([\d,]+)\s+stars?\s+today", t, re.I)
            if m:
                stars_today = int(m.group(1).replace(",", ""))
                break

        repos.append({
            "owner": owner,
            "name": name,
            "full_name": f"{owner}/{name}",
            "url": f"https://github.com/{owner}/{name}",
            "description": description,
            "language": language,
            "language_color": LANG_COLORS.get(language, "#8b8b8b"),
            "stars": stars,
            "forks": forks,
            "stars_today": stars_today,
        })
    return repos


def enrich_with_api(repos: list[dict], token: str | None) -> list[dict]:
    """Add avatar, today/total star deltas via API (best-effort, optional)."""
    if not token:
        print("  no GITHUB_TOKEN: skipping API enrichment", file=sys.stderr)
        return repos
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "gh-trending-daily-bot",
    }
    for repo in repos:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{repo['owner']}/{repo['name']}",
                headers=headers, timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                repo["avatar"] = data.get("owner", {}).get("avatar_url", "")
                # update total stars from canonical source
                if data.get("stargazers_count") is not None:
                    repo["stars"] = data["stargazers_count"]
                if data.get("forks_count") is not None:
                    repo["forks"] = data["forks_count"]
                if data.get("description") and not repo["description"]:
                    repo["description"] = data["description"]
                if data.get("language") and not repo["language"]:
                    lang = data["language"]
                    repo["language"] = lang
                    repo["language_color"] = LANG_COLORS.get(lang, "#8b8b8b")
            elif r.status_code == 403:
                print("  rate limited, stopping enrichment", file=sys.stderr)
                break
        except requests.RequestException as e:
            print(f"  enrich {repo['full_name']} failed: {e}", file=sys.stderr)
        time.sleep(SLEEP)
    return repos


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_file = out_dir / f"trending_{today}.json"

    print(f"[fetch] GET {TRENDING_URL}")
    html = fetch_trending_html()
    repos = parse_trending(html)
    print(f"[parse] {len(repos)} repos")

    token = os.environ.get("GITHUB_TOKEN") or _read_token_from_env_file()
    repos = enrich_with_api(repos, token)

    payload = {
        "date": today,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "https://github.com/trending?since=daily",
        "count": len(repos),
        "repos": repos,
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[write] {out_file} ({out_file.stat().st_size} bytes)")
    return 0


def _read_token_from_env_file() -> str | None:
    env_file = Path.home() / ".hermes" / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("GITHUB_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


if __name__ == "__main__":
    sys.exit(main())
