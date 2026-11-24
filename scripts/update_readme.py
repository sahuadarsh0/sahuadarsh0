#!/usr/bin/env python3
"""
Auto-updates the Open Source section of README.md between
<!-- oss-activity:start --> and <!-- oss-activity:end -->.

Zero external dependencies (Python 3 stdlib). Uses GITHUB_TOKEN if set,
falling back to `gh auth token` locally or unauthenticated public GitHub API.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

USERNAME = "sahuadarsh0"
README_PATH = Path(__file__).resolve().parent.parent / "README.md"
START_MARKER = "<!-- oss-activity:start -->"
END_MARKER = "<!-- oss-activity:end -->"
MAX_RECENT_PRS = 5
MAX_TOP_REPOS = 6


def _get_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    try:
        out = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL).strip()
        if out:
            return out
    except Exception:
        pass
    return ""


def _gh_get(url: str, token: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-updater",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_external_prs(token: str) -> list[dict]:
    items: list[dict] = []
    q = urllib.parse.quote(f"author:{USERNAME} type:pr -user:{USERNAME}")
    for page in (1, 2):
        url = f"https://api.github.com/search/issues?q={q}&sort=created&order=desc&per_page=100&page={page}"
        data = _gh_get(url, token)
        batch = data.get("items") or []
        items.extend(batch)
        if len(batch) < 100:
            break

    prs: list[dict] = []
    for it in items:
        repo_url = it.get("repository_url", "")
        m = re.search(r"/repos/([^/]+/[^/]+)$", repo_url)
        if not m:
            continue
        repo = m.group(1)
        if repo.lower().startswith(f"{USERNAME.lower()}/"):
            continue
        pr_meta = it.get("pull_request") or {}
        is_merged = bool(pr_meta.get("merged_at"))
        is_draft = bool(it.get("draft"))
        raw_state = (it.get("state") or "open").lower()
        if is_merged:
            status = "merged"
        elif raw_state == "closed":
            status = "closed"
        elif is_draft:
            status = "draft"
        else:
            status = "open"
        prs.append({
            "repo": repo,
            "number": int(it["number"]),
            "title": (it.get("title") or "").strip(),
            "url": it.get("html_url") or f"https://github.com/{repo}/pull/{it['number']}",
            "status": status,
            "created": (it.get("created_at") or "")[:10],
            "merged_at": (pr_meta.get("merged_at") or "")[:10],
        })
    return prs


def render_section(prs: list[dict]) -> str:
    # Exclude closed-unmerged PRs from public showcase counts/feed
    active_prs = [p for p in prs if p["status"] in ("merged", "open")]
    merged_cnt = sum(1 for p in active_prs if p["status"] == "merged")
    repo_counts = Counter(p["repo"] for p in active_prs)
    repo_merged = Counter(p["repo"] for p in active_prs if p["status"] == "merged")

    # Sort repos: merged count desc, total PRs desc, name asc
    ranked_repos = sorted(
        repo_counts.keys(),
        key=lambda r: (-repo_merged[r], -repo_counts[r], r.lower()),
    )

    top_links = [
        f"[`{r}`](https://github.com/{r})"
        for r in ranked_repos[:MAX_TOP_REPOS]
    ]
    extra = len(ranked_repos) - MAX_TOP_REPOS
    eco_line = " · ".join(top_links) + (f" · `+{extra} more`" if extra > 0 else "")

    # Rolling latest N PRs (merged & open, newest first)
    recent = active_prs[:MAX_RECENT_PRS]
    lines = [
        f"<sub>**{len(active_prs)}** external PRs · **{merged_cnt}** merged · **{len(ranked_repos)}** repositories · auto-updated</sub>",
        "",
        f"**Ecosystems**<br />{eco_line}",
        "",
        "**Recent Contributions**",
    ]
    for p in recent:
        short_repo = p["repo"]
        title = p["title"]
        if len(title) > 68:
            title = title[:65].rstrip() + "…"
        tag = "`merged`" if p["status"] == "merged" else "`open`"
        lines.append(f"- [**{short_repo}#{p['number']}**]({p['url']}) {tag} — {title}")

    return "\n".join(lines)


def main() -> None:
    token = _get_token()
    prs = fetch_external_prs(token)
    if not prs:
        print("No external PRs returned; leaving README untouched.")
        return

    body = render_section(prs)
    text = README_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START_MARKER) + r"[\s\S]*?" + re.escape(END_MARKER),
        re.MULTILINE,
    )
    replacement = f"{START_MARKER}\n{body}\n{END_MARKER}"
    if not pattern.search(text):
        raise SystemExit("README.md is missing oss-activity markers.")

    new_text = pattern.sub(lambda _: replacement, text, count=1)
    if new_text != text:
        README_PATH.write_text(new_text, encoding="utf-8")
        print(f"Updated README.md with {len(prs)} external PRs.")
    else:
        print("README.md already up to date.")


if __name__ == "__main__":
    main()
