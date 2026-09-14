"""Isolated XPO contact-discovery probe.

This script does not run MARKETIA collectors/scoring and does not write production feeds.
It tests a rebound source that is reachable from GitHub: GitHub's public code search API.

Usage:
    python scripts/xpo_contact_probe.py

Optional:
    GITHUB_TOKEN=... python scripts/xpo_contact_probe.py
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

COMPANY = "XPO Logistics"
ROLE_TERMS = [
    "Infrastructure & Cloud Director",
    "Infrastructure Director",
    "IT Infrastructure",
    "IT Director",
    "DSI",
    "CIO",
    "IT procurement",
    "IT buyer",
]


def request_json(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "MARKETIA-XPO-contact-probe/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def github_code_search(query: str) -> list[dict]:
    encoded = urllib.parse.quote(query)
    data = request_json(f"https://api.github.com/search/code?q={encoded}&per_page=10")
    return data.get("items", [])


def linkedin_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://(?:[a-z]{2}\.)?linkedin\.com/in/[A-Za-z0-9_%\-]+/?", text, flags=re.I)
    return list(dict.fromkeys(urls))


def main() -> None:
    report = {"company": COMPANY, "queries": [], "candidates": []}
    seen = set()
    for role in ROLE_TERMS:
        query = f'"{COMPANY}" "{role}" linkedin.com/in'
        row = {"query": query, "matches": 0, "error": None}
        try:
            items = github_code_search(query)
            row["matches"] = len(items)
            for item in items:
                html_url = item.get("html_url", "")
                key = (item.get("repository", {}).get("full_name", ""), item.get("path", ""))
                if key in seen:
                    continue
                seen.add(key)
                report["candidates"].append({
                    "role_query": role,
                    "repository": key[0],
                    "path": key[1],
                    "evidence_url": html_url,
                })
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        report["queries"].append(row)

    report["candidate_count"] = len(report["candidates"])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
