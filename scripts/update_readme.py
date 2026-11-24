#!/usr/bin/env python3
"""
Auto-updates README.md (between <!-- oss-activity:start/end -->) and generates
theme-aware telemetry SVGs (assets/telemetry-dark.svg & assets/telemetry-light.svg)
matching the obsidian + emerald hardware aesthetic of assets/banner.jpg.

Zero external dependencies (Python 3 stdlib).
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

USERNAME = "sahuadarsh0"
ROOT = Path(__file__).resolve().parent.parent
README_PATH = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets"
START_MARKER = "<!-- oss-activity:start -->"
END_MARKER = "<!-- oss-activity:end -->"
MAX_RECENT_PRS = 5
MAX_ECO_PILLS = 6


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


def _gh_get(url: str, token: str):
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


def fetch_repo_stats(token: str) -> tuple[int, list[tuple[str, float]]]:
    """Return (total_stars, [(lang, pct), ...]) from public non-fork repos."""
    repos = _gh_get(f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100", token)
    total_stars = 0
    lang_counts: Counter[str] = Counter()
    for r in repos:
        if r.get("fork"):
            continue
        total_stars += int(r.get("stargazers_count") or 0)
        lang = r.get("language")
        if lang and lang not in ("HTML", "CSS", "Shell"):
            # Weight by repo size (capped so one massive dump doesn't distort everything)
            sz = max(50, min(int(r.get("size") or 50), 15000))
            lang_counts[lang] += sz

    # Also boost Kotlin/Java weight slightly for external OSS PR ecosystems
    if not lang_counts:
        return total_stars, [("Kotlin", 62.0), ("Java", 22.0), ("Rust", 10.0), ("Python", 6.0)]

    top = lang_counts.most_common(5)
    tot = sum(v for _, v in top) or 1
    shares = [(k, round(v * 100.0 / tot, 1)) for k, v in top]
    return total_stars, shares


def render_telemetry_svg(
    *,
    dark: bool,
    pr_total: int,
    merged_total: int,
    repo_total: int,
    stars_total: int,
    ecosystems: list[str],
    languages: list[tuple[str, float]],
) -> str:
    if dark:
        bg = "#0d1117"
        panel = "#13171f"
        border = "#262c36"
        divider = "#21262d"
        fg = "#f4f4f5"
        muted = "#8b949e"
        subtle = "#6e7681"
        pill_bg = "#161b22"
        pill_border = "#2d333b"
        accent = "#34d399"
        bar_palette = ["#34d399", "#a1a1aa", "#d4a373", "#60a5fa", "#52525b"]
    else:
        bg = "#ffffff"
        panel = "#f6f8fa"
        border = "#d0d7de"
        divider = "#d8dee4"
        fg = "#1f2328"
        muted = "#59636e"
        subtle = "#6e7781"
        pill_bg = "#ffffff"
        pill_border = "#d0d7de"
        accent = "#059669"
        bar_palette = ["#059669", "#52525b", "#b45309", "#2563eb", "#94a3b8"]

    W, H = 860, 214
    # KPI columns
    kpis = [
        (str(pr_total), "EXTERNAL PRS", True),
        (str(merged_total), "MERGED", False),
        (str(repo_total), "REPOSITORIES", False),
        (str(stars_total), "STARS EARNED", False),
    ]
    kpi_svg = []
    col_w = (W - 48) / 4
    for i, (val, label, is_accent) in enumerate(kpis):
        x = 24 + i * col_w
        if i > 0:
            kpi_svg.append(f'  <line x1="{x:.1f}" y1="56" x2="{x:.1f}" y2="108" stroke="{divider}" stroke-width="1"/>')
        vx = x + 16
        val_fill = accent if is_accent else fg
        kpi_svg.append(
            f'  <text x="{vx:.1f}" y="86" fill="{val_fill}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" '
            f'font-size="28" font-weight="700" letter-spacing="-0.6">{html.escape(val)}</text>'
        )
        kpi_svg.append(
            f'  <text x="{vx:.1f}" y="105" fill="{muted}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
            f'font-size="10.5" font-weight="500" letter-spacing="1.1">{html.escape(label)}</text>'
        )

    # Segmented language bar (exact width budget — zero overshoot)
    bar_x, bar_y, bar_w, bar_h = 36.0, 134.0, float(W - 72), 8.0
    bar_segs = []
    legend_svg = []
    gap = 3.0
    n_langs = len(languages)
    usable_w = bar_w - max(0, n_langs - 1) * gap
    pct_sum = sum(p for _, p in languages) or 100.0
    raw_ws = [max(8.0, usable_w * (p / pct_sum)) for _, p in languages]
    scale = usable_w / (sum(raw_ws) or 1.0)
    seg_ws = [w * scale for w in raw_ws]

    cur_x = bar_x
    leg_x = bar_x
    for idx, ((lang, pct), seg_w) in enumerate(zip(languages, seg_ws)):
        col = bar_palette[idx % len(bar_palette)]
        bar_segs.append(f'  <rect x="{cur_x:.1f}" y="{bar_y:.1f}" width="{seg_w:.1f}" height="{bar_h:.1f}" rx="3" fill="{col}"/>')
        cur_x += seg_w + gap
        legend_svg.append(f'  <circle cx="{leg_x + 4:.1f}" cy="157" r="3.5" fill="{col}"/>')
        lbl = f"{lang} {pct:.0f}%"
        legend_svg.append(
            f'  <text x="{leg_x + 13:.1f}" y="161" fill="{muted}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
            f'font-size="11">{html.escape(lbl)}</text>'
        )
        leg_x += len(lbl) * 7.1 + 26

    # Ecosystem pills row
    pills_svg = []
    px = 36.0
    shown = ecosystems[:MAX_ECO_PILLS]
    extra = len(ecosystems) - len(shown)
    labels = list(shown) + ([f"+{extra} more"] if extra > 0 else [])
    for idx, eco in enumerate(labels):
        disp = eco if len(eco) <= 20 else eco.split("/", 1)[-1]
        pw = len(disp) * 6.7 + 18
        if px + pw > W - 36:
            rem = len(ecosystems) - idx
            if rem > 0 and not eco.startswith("+"):
                disp = f"+{rem} more"
                pw = len(disp) * 6.7 + 18
                if px + pw <= W - 32:
                    pills_svg.append(
                        f'  <rect x="{px:.1f}" y="176" width="{pw:.1f}" height="24" rx="6" fill="{pill_bg}" stroke="{pill_border}" stroke-width="1"/>'
                    )
                    pills_svg.append(
                        f'  <text x="{px + 9:.1f}" y="191.5" fill="{subtle}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
                        f'font-size="11">{html.escape(disp)}</text>'
                    )
            break
        txt_col = subtle if eco.startswith("+") else fg
        pills_svg.append(
            f'  <rect x="{px:.1f}" y="176" width="{pw:.1f}" height="24" rx="6" fill="{pill_bg}" stroke="{pill_border}" stroke-width="1"/>'
        )
        pills_svg.append(
            f'  <text x="{px + 9:.1f}" y="191.5" fill="{txt_col}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
            f'font-size="11">{html.escape(disp)}</text>'
        )
        px += pw + 8

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none">',
        f'  <rect x="0.75" y="0.75" width="{W - 1.5}" height="{H - 1.5}" rx="12" fill="{panel}" stroke="{border}" stroke-width="1.2"/>',
        f'  <circle cx="36" cy="28" r="3.5" fill="{accent}"/>',
        f'  <text x="48" y="32" fill="{muted}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="11" font-weight="600" letter-spacing="1.4">OPEN SOURCE TELEMETRY</text>',
        f'  <text x="{W - 36}" y="32" text-anchor="end" fill="{subtle}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="10.5" letter-spacing="0.8">AUTO-SYNCED · GITHUB</text>',
        f'  <line x1="24" y1="44" x2="{W - 24}" y2="44" stroke="{divider}" stroke-width="1"/>',
        *kpi_svg,
        f'  <line x1="24" y1="120" x2="{W - 24}" y2="120" stroke="{divider}" stroke-width="1"/>',
        *bar_segs,
        *legend_svg,
        *pills_svg,
        "</svg>",
        "",
    ])


def render_recent_markdown(active_prs: list[dict]) -> str:
    recent = active_prs[:MAX_RECENT_PRS]
    lines: list[str] = []
    for p in recent:
        title = p["title"]
        if len(title) > 78:
            title = title[:75].rstrip() + "…"
        tag = "`merged`" if p["status"] == "merged" else "`open`"
        lines.append(f"- [**{p['repo']}#{p['number']}**]({p['url']}) &nbsp;{tag}&nbsp; — {title}")
    return "\n".join(lines)


def main() -> None:
    token = _get_token()
    prs = fetch_external_prs(token)
    if not prs:
        print("No external PRs returned; leaving files untouched.")
        return

    active_prs = [p for p in prs if p["status"] in ("merged", "open")]
    merged_cnt = sum(1 for p in active_prs if p["status"] == "merged")
    repo_counts = Counter(p["repo"] for p in active_prs)
    repo_merged = Counter(p["repo"] for p in active_prs if p["status"] == "merged")
    repo_latest: dict[str, str] = {}
    for p in active_prs:
        r = p["repo"]
        if p["created"] > repo_latest.get(r, ""):
            repo_latest[r] = p["created"]

    ranked_repos = sorted(
        repo_counts.keys(),
        key=lambda r: (-(repo_counts[r] + repo_merged[r]), repo_latest.get(r, "") < "2026-01-01", -repo_counts[r], r.lower()),
    )

    stars_total, lang_shares = fetch_repo_stats(token)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for dark, fname in ((True, "telemetry-dark.svg"), (False, "telemetry-light.svg")):
        svg = render_telemetry_svg(
            dark=dark,
            pr_total=len(active_prs),
            merged_total=merged_cnt,
            repo_total=len(ranked_repos),
            stars_total=stars_total,
            ecosystems=ranked_repos,
            languages=lang_shares,
        )
        (ASSETS_DIR / fname).write_text(svg, encoding="utf-8")

    body = render_recent_markdown(active_prs)
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
    print(f"Synced telemetry SVGs & README ({len(active_prs)} PRs, {merged_cnt} merged, {len(ranked_repos)} repos, {stars_total} stars).")


if __name__ == "__main__":
    main()
