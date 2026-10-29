#!/usr/bin/env python3
"""
Neofetch-style GitHub profile card.

Fetches your GitHub stats (repos, stars, followers, commits, lines of code)
and renders dark_mode.svg + light_mode.svg from config.json + ascii.txt
(+ ascii_dark.txt for the dark card, if present).

Usage:
    ACCESS_TOKEN=ghp_xxx python card.py   # fetch live stats, then render
    python card.py --offline              # render using cached stats only
    python card.py --demo                 # render with fake numbers (preview)

Standard library only, so the GitHub Action needs no pip install.
"""
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
ASCII = ROOT / "ascii.txt"
ASCII_DARK = ROOT / "ascii_dark.txt"  # optional: art for the dark card (light ink)
STATS_CACHE = ROOT / "cache" / "stats.json"
LOC_CACHE = ROOT / "cache" / "loc.json"

WIDTH = 60          # characters in the info column
FONT_PX = 16
LINE_PX = 20
CHAR_PX = 10.2      # generous: fonts differ by viewer (Consolas ~8.8px, Menlo/DejaVu ~9.6px)
PAD = 15

# The ascii art gets its own smaller font so a detailed portrait (~104x52)
# fits in the same box as the info column. Keep ART_LINE_PX / real glyph
# width ~= make_ascii.py's CHAR_ASPECT.
ART_FONT_PX = 6
ART_LINE_PX = 7.5
ART_CHAR_PX = 3.9

THEMES = {
    "dark": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 cc="#616e7f", add="#3fb950", dele="#f85149", art="#c9d1d9"),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                  cc="#c2cfde", add="#1a7f37", dele="#cf222e", art="#24292f"),
}

# --------------------------------------------------------------------------- #
# GitHub API
# --------------------------------------------------------------------------- #
API = "https://api.github.com/graphql"


def gql(query, variables, token, retries=4):
    body = json.dumps({"query": query, "variables": variables}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-card",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            if "errors" in data and not data.get("data"):
                raise RuntimeError(data["errors"])
            return data["data"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            # GitHub's GraphQL often 502s on big history queries; back off and retry
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1} after {e}", file=sys.stderr)
            time.sleep(2 ** attempt * 3)


USER_Q = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    id
    createdAt
    followers { totalCount }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
    owned: repositories(ownerAffiliations: [OWNER], first: 1) { totalCount }
    repos: repositories(first: 100, after: $cursor,
                        ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
      pageInfo { endCursor hasNextPage }
      nodes { nameWithOwner stargazerCount owner { login } }
    }
  }
}"""

HISTORY_Q = """
query($owner: String!, $name: String!, $cursor: String, $author: ID!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor, author: {id: $author}) {
            totalCount
            pageInfo { endCursor hasNextPage }
            nodes { additions deletions }
          }
        }
      }
    }
  }
}"""


def repo_history(owner, name, author_id, token, known_count=None):
    """Return (commits, additions, deletions) for your commits on the default branch.
    If known_count matches the current commit count, returns None (cache is still valid)."""
    cursor, commits, add, dele = None, 0, 0, 0
    first = True
    while True:
        d = gql(HISTORY_Q, {"owner": owner, "name": name, "cursor": cursor,
                            "author": author_id}, token)
        ref = (d.get("repository") or {}).get("defaultBranchRef")
        if not ref:                          # empty repo
            return (0, 0, 0)
        h = ref["target"]["history"]
        if first:
            commits = h["totalCount"]
            if known_count is not None and commits == known_count:
                return None
            first = False
        for n in h["nodes"]:
            add += n["additions"]
            dele += n["deletions"]
        if not h["pageInfo"]["hasNextPage"]:
            return (commits, add, dele)
        cursor = h["pageInfo"]["endCursor"]


def fetch_stats(login, token):
    print(f"Fetching stats for {login}...")
    cursor, repos, user = None, [], None
    while True:
        d = gql(USER_Q, {"login": login, "cursor": cursor}, token)
        user = d["user"]
        repos += user["repos"]["nodes"]
        if not user["repos"]["pageInfo"]["hasNextPage"]:
            break
        cursor = user["repos"]["pageInfo"]["endCursor"]

    stars = sum(r["stargazerCount"] for r in repos
                if r["owner"]["login"].lower() == login.lower())

    # Lines of code. Cache is keyed by a hash of the repo name so private repo
    # names never end up in this public repository.
    loc_cache = json.loads(LOC_CACHE.read_text()) if LOC_CACHE.exists() else {}
    new_cache = {}
    for r in repos:
        key = hashlib.sha256(r["nameWithOwner"].encode()).hexdigest()
        owner, name = r["nameWithOwner"].split("/", 1)
        cached = loc_cache.get(key)
        try:
            res = repo_history(owner, name, user["id"], token,
                               known_count=cached["commits"] if cached else None)
        except Exception as e:               # keep old numbers if one repo misbehaves
            print(f"  skip {r['nameWithOwner']}: {e}", file=sys.stderr)
            res = None if cached else (0, 0, 0)
        if res is None:
            new_cache[key] = cached
        else:
            new_cache[key] = dict(zip(("commits", "additions", "deletions"), res))

    LOC_CACHE.parent.mkdir(exist_ok=True)
    LOC_CACHE.write_text(json.dumps(new_cache, indent=1, sort_keys=True))

    add = sum(v["additions"] for v in new_cache.values())
    dele = sum(v["deletions"] for v in new_cache.values())
    stats = {
        "created_at": user["createdAt"],
        "repos": user["owned"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "followers": user["followers"]["totalCount"],
        "commits": sum(v["commits"] for v in new_cache.values()),
        "additions": add,
        "deletions": dele,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    STATS_CACHE.write_text(json.dumps(stats, indent=1))
    return stats


DEMO_STATS = {"created_at": "2021-08-20T00:00:00Z", "repos": 34, "contributed": 12,
              "stars": 27, "followers": 41, "commits": 1287,
              "additions": 184_320, "deletions": 52_116}

# --------------------------------------------------------------------------- #
# Text layout
# --------------------------------------------------------------------------- #


def age(start, today=None):
    today = today or dt.date.today()
    y, m, d = today.year - start.year, today.month - start.month, today.day - start.day
    if d < 0:
        m -= 1
        prev_month = (today.replace(day=1) - dt.timedelta(days=1))
        d += prev_month.day
    if m < 0:
        y -= 1
        m += 12
    s = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{s(y, 'year')}, {s(m, 'month')}, {s(d, 'day')}"


def kv(key, value, width, prefix=". "):
    """'. Key: ........ value' padded to `width`. value may be str or [(cls, text)]."""
    vsegs = [("value", value)] if isinstance(value, str) else value
    vlen = sum(len(t) for _, t in vsegs)
    key_part = f"{key}:"
    n = max(1, width - len(prefix) - len(key_part) - vlen - 2)
    return [("cc", prefix), ("key", key_part), ("cc", f" {'.' * n} ")] + vsegs


def rule(label, width):
    head = f"- {label} -" if label else "-"
    return [("text", head), ("cc", "—" * (width - len(head) - 3) + "-—-")]


def build_lines(cfg, stats):
    lines = [[("key", cfg["prompt"]), ("cc", " -" + "—" * (WIDTH - len(cfg["prompt"]) - 5) + "-—-")]]

    uptime = ""
    if cfg.get("birthday"):
        uptime = age(dt.date.fromisoformat(cfg["birthday"]))
    elif stats and stats.get("created_at"):
        uptime = age(dt.date.fromisoformat(stats["created_at"][:10])) + " on GH"

    for sec in cfg["sections"]:
        if sec.get("title"):
            lines.append(rule(sec["title"], WIDTH))
        for key, val in sec["lines"]:
            if key == "" and val == "":
                lines.append([("cc", ". ")])
                continue
            val = val.replace("{uptime}", uptime)
            if val:
                lines.append(kv(key, val, WIDTH))

    if stats:
        f = lambda n: f"{n:,}"
        left = 34
        right = WIDTH - left - 3
        lines.append(rule("GitHub Stats", WIDTH))
        lines.append(kv("Repos", [("value", f(stats["repos"])), ("cc", " {"),
                                  ("key", "Contributed: "), ("value", f(stats["contributed"])),
                                  ("cc", "}")], left)
                     + [("cc", " | ")] + kv("Stars", f(stats["stars"]), right, prefix=""))
        lines.append(kv("Commits", f(stats["commits"]), left)
                     + [("cc", " | ")] + kv("Followers", f(stats["followers"]), right, prefix=""))
        loc = stats["additions"] - stats["deletions"]
        lines.append(kv("Lines of Code",
                        [("value", f(loc)), ("cc", " ( "),
                         ("add", f(stats["additions"]) + "++"), ("cc", ", "),
                         ("dele", f(stats["deletions"]) + "--"), ("cc", " )")], WIDTH))
    return lines

# --------------------------------------------------------------------------- #
# SVG
# --------------------------------------------------------------------------- #


def render_svg(theme, art, lines):
    c = THEMES[theme]
    art_cols = max((len(l) for l in art), default=0)
    info_x = PAD + art_cols * ART_CHAR_PX + (25 if art_cols else 0)
    w = round(info_x + WIDTH * CHAR_PX + PAD)
    h = round(max(len(art) * ART_LINE_PX, len(lines) * LINE_PX)) + 2 * PAD
    y0 = PAD + LINE_PX - 4
    art_y0 = PAD + ART_LINE_PX - 2

    out = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}px" height="{h}px" font-size="{FONT_PX}px">',
        "<style>",
        "@font-face { font-family: ConsolasFallback; src: local('Consolas'); }",
        f".text {{ fill: {c['text']}; }} .key {{ fill: {c['key']}; }} .value {{ fill: {c['value']}; }}",
        f".cc {{ fill: {c['cc']}; }} .add {{ fill: {c['add']}; }} .dele {{ fill: {c['dele']}; }}",
        "text, tspan { white-space: pre; font-family: ConsolasFallback, Consolas, 'DejaVu Sans Mono', Menlo, monospace; }",
        "</style>",
        f'<rect width="{w}px" height="{h}px" fill="{c["bg"]}" rx="15"/>',
        f'<text x="{PAD}" y="{art_y0}" fill="{c["art"]}" font-size="{ART_FONT_PX}px" xml:space="preserve">',
    ]
    for i, l in enumerate(art):
        out.append(f'<tspan x="{PAD}" y="{art_y0 + i * ART_LINE_PX}">{escape(l)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{info_x:.0f}" y="{y0}" fill="{c["text"]}" xml:space="preserve">')
    for i, segs in enumerate(lines):
        y = y0 + i * LINE_PX
        inner = "".join(f'<tspan class="{cls}">{escape(t)}</tspan>' for cls, t in segs)
        out.append(f'<tspan x="{info_x:.0f}" y="{y}">{inner}</tspan>')
    out.append("</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    cfg = json.loads(CONFIG.read_text())
    read_art = lambda p: p.read_text().rstrip("\n").split("\n") if p.exists() else []
    art = {"light": read_art(ASCII)}
    art["dark"] = read_art(ASCII_DARK) if ASCII_DARK.exists() else art["light"]

    stats = None
    if "--demo" in sys.argv:
        stats = DEMO_STATS
    elif "--offline" not in sys.argv and os.environ.get("ACCESS_TOKEN"):
        try:
            stats = fetch_stats(cfg["github_username"], os.environ["ACCESS_TOKEN"])
        except Exception as e:
            print(f"Fetch failed ({e}); falling back to cached stats", file=sys.stderr)
    if stats is None and STATS_CACHE.exists():
        stats = json.loads(STATS_CACHE.read_text())
    if stats is None:
        print("No token and no cached stats: rendering without the stats block.")

    lines = build_lines(cfg, stats)
    for l in lines:
        n = sum(len(t) for _, t in l)
        if n > WIDTH:
            print(f"warning: line is {n} chars (> {WIDTH}), shorten it: "
                  + "".join(t for _, t in l), file=sys.stderr)
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render_svg(theme, art[theme], lines))
    print("Wrote dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()
