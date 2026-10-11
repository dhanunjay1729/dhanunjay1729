#!/usr/bin/env python3
"""Build profile SVGs from GitHub public data; uses only the Python standard library."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
COLORS = {"JavaScript": "#d9b800", "TypeScript": "#3178c6", "Python": "#3572a5",
          "HTML": "#e34c26", "CSS": "#7957d5", "Go": "#00add8", "EJS": "#7b9c24"}


class GitHub:
    def __init__(self):
        self.headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats",
                        "X-GitHub-Api-Version": "2026-03-10"}
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            self.headers["Authorization"] = "Bearer " + token

    def get(self, path, params=None, empty_repository=False):
        url = path if path.startswith("https://") else API + path
        if urlparse(url).netloc != "api.github.com":
            raise ValueError("Unexpected API host")
        if params:
            url += "?" + urlencode(params)
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers=self.headers), timeout=30) as response:
                    payload = json.load(response)
                    return payload, response.headers.get("Link", "")
            except HTTPError as exc:
                message = exc.read().decode("utf-8", errors="replace")
                if empty_repository and exc.code == 409 and "Git Repository is empty" in message:
                    return [], ""
                if attempt < 2 and exc.code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"GitHub returned HTTP {exc.code} for {url}") from exc
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))

    def pages(self, path, params=None, empty_repository=False):
        payload, links = self.get(path, params, empty_repository)
        if not isinstance(payload, list):
            raise ValueError("Expected a GitHub list response")
        result = list(payload)
        while True:
            match = re.search(r'<([^>]+)>; rel="next"', links)
            if not match:
                return result
            payload, links = self.get(match.group(1), empty_repository=empty_repository)
            if not isinstance(payload, list):
                raise ValueError("Expected a paginated GitHub list response")
            result.extend(payload)


def collect(username):
    api = GitHub()
    repos = api.pages(f"/users/{username}/repos", {"type": "owner", "per_page": 100})
    repos = [r for r in repos if not r["private"] and
             r["owner"]["login"].lower() == username.lower()]
    languages = Counter()
    commits = set()
    evidence = []
    for repo in sorted(repos, key=lambda r: r["name"].lower()):
        name = repo["full_name"]
        authored = api.pages(f"/repos/{name}/commits", {"author": username, "per_page": 100},
                             empty_repository=True)
        shas = {c["sha"] for c in authored}
        commits.update(shas)
        by_language = {}
        if not repo["fork"]:
            by_language, _ = api.get(f"/repos/{name}/languages")
            if not isinstance(by_language, dict) or not all(isinstance(v, int) for v in by_language.values()):
                raise ValueError("Invalid language response")
            languages.update(by_language)
        evidence.append({"name": name, "fork": repo["fork"], "stars": repo["stargazers_count"],
                         "authored_commit_shas": sorted(shas), "language_bytes": by_language})
    prs, _ = api.get("/search/issues", {"q": f"author:{username} type:pr is:public", "per_page": 1})
    if prs.get("incomplete_results", True) or not isinstance(prs.get("total_count"), int):
        raise ValueError("Incomplete public pull-request search; preserving previous cards")
    return {"username": username, "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "metrics": {"public_repositories": len(repos), "authored_commits": len(commits),
                        "public_pull_requests": prs["total_count"],
                        "stars_received": sum(r["stargazers_count"] for r in repos if not r["fork"])},
            "language_bytes": dict(sorted(languages.items())), "repositories": evidence}


def validate(data):
    if not re.fullmatch(r"[A-Za-z0-9-]+", data["username"]):
        raise ValueError("Invalid username")
    datetime.strptime(data["updated_at"], "%Y-%m-%d")
    for key in ("public_repositories", "authored_commits", "public_pull_requests", "stars_received"):
        value = data["metrics"][key]
        if type(value) is not int or value < 0:
            raise ValueError(f"Invalid metric: {key}")
    if not all(type(v) is int and v >= 0 for v in data["language_bytes"].values()):
        raise ValueError("Invalid language totals")


def svg_header(title, description, theme, height=214):
    dark = theme == "dark"
    bg, fg, muted, border = ("#0d1117", "#e6edf3", "#9da7b3", "#30363d") if dark else (
        "#ffffff", "#1f2328", "#59636e", "#d1d9e0")
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="440" height="{height}" viewBox="0 0 440 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>',
            f'<rect x=".5" y=".5" width="439" height="{height-1}" rx="10" fill="{bg}" stroke="{border}"/>',
            f'<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" fill="{fg}">',
            f'<text x="22" y="32" font-size="16" font-weight="600">{escape(title)}</text>'], fg, muted


def stats_svg(data, theme):
    m = data["metrics"]
    metrics = [("Public repositories", m["public_repositories"]),
               ("Authored commits", m["authored_commits"]),
               ("Pull requests", m["public_pull_requests"]), ("Stars received", m["stars_received"])]
    description = "; ".join(f"{label}: {value}" for label, value in metrics)
    parts, _, muted = svg_header("GitHub activity", description, theme)
    for (label, value), (x, y) in zip(metrics, [(22, 74), (235, 74), (22, 134), (235, 134)]):
        parts.extend([f'<text x="{x}" y="{y}" font-size="25" font-weight="600">{value:,}</text>',
                      f'<text x="{x}" y="{y+21}" font-size="12" fill="{muted}">{label}</text>'])
    parts.extend([f'<text x="22" y="192" font-size="11" fill="{muted}">Public data · Updated {data["updated_at"]}</text>', "</g></svg>"])
    return "\n".join(parts) + "\n"


def language_groups(data):
    ordered = sorted(((k, v) for k, v in data["language_bytes"].items()
                      if k != "Jupyter Notebook" and v > 0), key=lambda item: (-item[1], item[0]))
    groups = ordered[:5]
    if len(ordered) > 5:
        groups.append(("Other", sum(v for _, v in ordered[5:])))
    return groups


def languages_svg(data, theme):
    groups = language_groups(data)
    total = sum(v for _, v in groups)
    description = "Source bytes in owned public non-fork repositories; notebook files excluded. "
    description += "; ".join(f"{k}: {v / total * 100:.1f}%" for k, v in groups) if total else "No source bytes."
    parts, _, muted = svg_header("Languages in public repos", description, theme)
    parts.append(f'<text x="22" y="55" font-size="11" fill="{muted}">Source bytes · Notebook files and forks excluded</text>')
    parts.append('<defs><clipPath id="bar"><rect x="22" y="69" width="396" height="9" rx="4"/></clipPath></defs>')
    offset = 22.0
    for name, value in groups:
        width = 396 * value / total
        parts.append(f'<rect x="{offset:.4f}" y="69" width="{width:.4f}" height="9" fill="{COLORS.get(name, "#8b949e")}" clip-path="url(#bar)"/>')
        offset += width
    for i, (name, value) in enumerate(groups):
        x, y = 22 + (i % 2) * 205, 104 + (i // 2) * 26
        color = COLORS.get(name, "#8b949e")
        parts.extend([f'<circle cx="{x+4}" cy="{y-4}" r="4" fill="{color}"/>',
                      f'<text x="{x+16}" y="{y}" font-size="12">{escape(name)}</text>',
                      f'<text x="{x+190}" y="{y}" text-anchor="end" font-size="12" fill="{muted}">{value / total * 100:.1f}%</text>'])
    if not total:
        parts.append(f'<text x="22" y="110" font-size="13" fill="{muted}">No source-language data available.</text>')
    parts.extend([f'<text x="22" y="192" font-size="11" fill="{muted}">Updated {data["updated_at"]}</text>', "</g></svg>"])
    return "\n".join(parts) + "\n"


def write_assets(data, output):
    validate(data)
    # Render everything first. A failed API request or validation leaves the last good files intact.
    rendered = {"stats-data.json": json.dumps(data, indent=2, sort_keys=True) + "\n"}
    for theme in ("light", "dark"):
        rendered[f"github-stats-{theme}.svg"] = stats_svg(data, theme)
        rendered[f"languages-{theme}.svg"] = languages_svg(data, theme)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.items():
        temp = output / (name + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(output / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="dhanunjay1729")
    parser.add_argument("--input", type=Path, help="Render a previously collected JSON snapshot without network access")
    parser.add_argument("--output", type=Path, default=ROOT / "assets")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.username):
        parser.error("Invalid GitHub username")
    data = json.loads(args.input.read_text(encoding="utf-8")) if args.input else collect(args.username)
    write_assets(data, args.output)
    print(json.dumps({"updated_at": data["updated_at"], "metrics": data["metrics"]}))


if __name__ == "__main__":
    main()
