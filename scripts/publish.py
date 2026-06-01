#!/usr/bin/env python3
"""
Commit site/ to git and push to GitHub Pages.

Workflow:
  1. Read GITHUB_TOKEN, GH_OWNER, GH_REPO from env (~/.hermes/.env)
  2. `git add` site/ + (optionally) data/ + scripts/ snapshot
  3. `git commit` with a date-stamped message
  4. `git push` using token-authenticated remote URL
  5. Print the public Pages URL on success
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SITE = BASE / "site"


def _load_env() -> dict:
    env = {}
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    # current process env wins
    env.update({k: v for k, v in os.environ.items()})
    return env


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def main() -> int:
    env = _load_env()
    token = env.get("GITHUB_TOKEN")
    owner = env.get("GH_OWNER")
    repo = env.get("GH_REPO", "gh-trending-daily")

    missing = [k for k, v in [("GITHUB_TOKEN", token), ("GH_OWNER", owner)] if not v]
    if missing:
        print(f"[error] missing required config: {missing}", file=sys.stderr)
        print(f"  add to ~/.hermes/.env:", file=sys.stderr)
        print(f"    GITHUB_TOKEN=ghp_xxx...", file=sys.stderr)
        print(f"    GH_OWNER={owner or '<your-github-username>'}", file=sys.stderr)
        print(f"    GH_REPO={repo}  # optional, default: gh-trending-daily", file=sys.stderr)
        return 1

    if not SITE.exists() or not (SITE / "index.html").exists():
        print(f"[error] no site/index.html found. run render_html.py first.", file=sys.stderr)
        return 1

    # 1. ensure local git repo
    if not (BASE / ".git").exists():
        print("[init] git init")
        _run(["git", "init", "-b", "main"], cwd=BASE)
        _run(["git", "config", "user.name", "gh-trending-daily bot"], cwd=BASE)
        _run(["git", "config", "user.email", "bot@localhost"], cwd=BASE)
        # also commit the source code (scripts/, README) on first run
        _run(["git", "add", "scripts/", "data/", ".gitignore", "README.md"], cwd=BASE)
        _run(["git", "commit", "-m", "chore: initial commit (source + first data snapshot)"], cwd=BASE)
        _run(["git", "branch", "-M", "main"], cwd=BASE)

    # 2. set up remote with token
    remote_url = f"https://{token}@github.com/{owner}/{repo}.git"
    # check if remote already set correctly
    try:
        existing = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=BASE, capture_output=True, text=True, check=False,
        )
        if existing.returncode != 0 or owner not in existing.stdout:
            if existing.returncode == 0:
                _run(["git", "remote", "remove", "origin"], cwd=BASE)
            _run(["git", "remote", "add", "origin", remote_url], cwd=BASE)
            print(f"  remote origin → {remote_url.replace(token, '***')}")
    except Exception:
        _run(["git", "remote", "add", "origin", remote_url], cwd=BASE)

    # 3. ensure gh-pages branch exists (Pages source = gh-pages branch)
    # Actually, simpler: just publish site/ to a gh-pages branch using `git worktree`
    # But easiest: push to main, the repo settings will have Pages set to main/root or gh-pages.
    # We'll push site/ contents to a gh-pages branch.
    ghpages_dir = BASE / ".gh-pages"
    if ghpages_dir.exists():
        _run(["git", "worktree", "remove", "--force", ".gh-pages"], cwd=BASE)
    _run(["git", "branch", "-D", "gh-pages"], cwd=BASE)
    _run(["git", "worktree", "add", "--branch", "gh-pages", ".gh-pages", "main"], cwd=BASE)
    # copy site/ contents into the worktree
    _run(["bash", "-c", "rm -rf .gh-pages/* && cp -r site/* .gh-pages/"], cwd=BASE)
    # also add a .nojekyll so Pages doesn't try to process the html
    (BASE / ".gh-pages" / ".nojekyll").write_text("")
    _run(["git", "add", "-A"], cwd=BASE / ".gh-pages")
    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"publish: trending report for {today}"
    # only commit if there are changes
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=BASE / ".gh-pages", capture_output=True, text=True,
    )
    if status.stdout.strip():
        _run(["git", "commit", "-m", msg], cwd=BASE / ".gh-pages")
        print(f"[commit] {msg}")
    else:
        print(f"[skip] no changes to publish")

    # 4. push
    print("[push] pushing gh-pages branch…")
    _run(["git", "push", "origin", "gh-pages", "--force"], cwd=BASE / ".gh-pages")
    # also push the main branch with the source code (in case GH_OWNER+GH_REPO is brand-new)
    try:
        _run(["git", "push", "-u", "origin", "main"], cwd=BASE)
    except subprocess.CalledProcessError as e:
        print(f"  (main branch push failed — may be empty remote, continuing): {e.stderr.strip()}", file=sys.stderr)

    pages_url = f"https://{owner}.github.io/{repo}/"
    print(f"\n[done] public URL: {pages_url}")
    print(f"  (Pages may take 1-2 minutes to deploy the first time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
