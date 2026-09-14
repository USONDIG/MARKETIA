from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

TAG_RE = re.compile(r"<[^>]+>")
DDG_RESULT_RE = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
DDG_SNIPPET_RE = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
BING_RESULT_RE = re.compile(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>.*?<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<p[^>]*>(.*?)</p>)?', re.I | re.S)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _unwrap_ddg(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else url
    return html.unescape(url)


def search_duckduckgo(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"}, timeout=timeout)
    response.raise_for_status()
    anchors = DDG_RESULT_RE.findall(response.text)
    snippets = DDG_SNIPPET_RE.findall(response.text)
    rows = []
    for idx, (raw_url, raw_title) in enumerate(anchors[:max_results]):
        url = _unwrap_ddg(raw_url)
        if url.startswith("http"):
            rows.append({"url": url, "title": _clean(raw_title), "snippet": _clean(snippets[idx]) if idx < len(snippets) else "", "provider": "duckduckgo"})
    return rows


def search_bing(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get("https://www.bing.com/search", params={"q": query, "setlang": "fr"}, headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"}, timeout=timeout)
    response.raise_for_status()
    rows = []
    for raw_url, raw_title, raw_snippet in BING_RESULT_RE.findall(response.text)[:max_results]:
        url = html.unescape(raw_url)
        if url.startswith("http"):
            rows.append({"url": url, "title": _clean(raw_title), "snippet": _clean(raw_snippet or ""), "provider": "bing"})
    return rows


def search_public_web(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    failures = []
    for provider in (search_duckduckgo, search_bing):
        try:
            rows = provider(query, timeout, user_agent, max_results)
            if rows:
                return rows
        except requests.RequestException as exc:
            failures.append(exc)
    if failures:
        raise requests.RequestException("No public search provider available") from failures[-1]
    return []
