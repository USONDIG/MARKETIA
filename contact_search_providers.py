from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

TAG_RE = re.compile(r"<[^>]+>")
DDG_RESULT_RE = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
DDG_SNIPPET_RE = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
BING_BLOCK_RE = re.compile(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', re.I | re.S)
ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
PARAGRAPH_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.I | re.S)
GOOGLE_RESULT_RE = re.compile(r'<a[^>]+href="/url\?q=([^&"]+)[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
GOOGLE_DIRECT_RE = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>', re.I | re.S)
YAHOO_RESULT_RE = re.compile(r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _unwrap_ddg(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else url
    return html.unescape(url)


def _unwrap_yahoo(url: str) -> str:
    value = html.unescape(url)
    match = re.search(r"/RU=([^/]+)/RK=", value)
    return unquote(match.group(1)) if match else value


def _valid_result(url: str) -> bool:
    if not url.startswith("http"):
        return False
    host = urlparse(url).netloc.casefold()
    return not any(name in host for name in ("google.com", "google.fr", "bing.com", "duckduckgo.com", "search.yahoo.com"))


def search_duckduckgo(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"}, timeout=timeout)
    response.raise_for_status()
    anchors = DDG_RESULT_RE.findall(response.text)
    snippets = DDG_SNIPPET_RE.findall(response.text)
    rows = []
    for idx, (raw_url, raw_title) in enumerate(anchors[:max_results]):
        url = _unwrap_ddg(raw_url)
        if _valid_result(url):
            rows.append({"url": url, "title": _clean(raw_title), "snippet": _clean(snippets[idx]) if idx < len(snippets) else "", "provider": "duckduckgo"})
    return rows


def search_bing(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get("https://www.bing.com/search", params={"q": query, "setlang": "fr", "count": max(10, max_results)}, headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"}, timeout=timeout)
    response.raise_for_status()
    rows = []
    for block in BING_BLOCK_RE.findall(response.text):
        anchor = ANCHOR_RE.search(block)
        if not anchor:
            continue
        url, raw_title = html.unescape(anchor.group(1)), anchor.group(2)
        if not _valid_result(url):
            continue
        paragraph = PARAGRAPH_RE.search(block)
        rows.append({"url": url, "title": _clean(raw_title), "snippet": _clean(paragraph.group(1)) if paragraph else "", "provider": "bing"})
        if len(rows) >= max_results:
            break
    return rows


def search_google(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get("https://www.google.com/search", params={"q": query, "num": min(10, max_results), "hl": "fr", "filter": "0"}, headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"}, timeout=timeout)
    response.raise_for_status()
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    matches = [(unquote(url), title) for url, title in GOOGLE_RESULT_RE.findall(response.text)]
    matches.extend(GOOGLE_DIRECT_RE.findall(response.text))
    for url, raw_title in matches:
        url = html.unescape(url)
        if url in seen or not _valid_result(url):
            continue
        seen.add(url)
        title = _clean(raw_title)
        if not title:
            continue
        rows.append({"url": url, "title": title, "snippet": "", "provider": "google"})
        if len(rows) >= max_results:
            break
    return rows


def search_yahoo(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get("https://search.yahoo.com/search", params={"p": query}, headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"}, timeout=timeout)
    response.raise_for_status()
    rows = []
    for raw_url, raw_title in YAHOO_RESULT_RE.findall(response.text):
        url = _unwrap_yahoo(raw_url)
        if not _valid_result(url):
            continue
        rows.append({"url": url, "title": _clean(raw_title), "snippet": "", "provider": "yahoo"})
        if len(rows) >= max_results:
            break
    return rows


def search_public_web(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    """Search public web with independent fallbacks suitable for unattended runners."""
    failures = []
    for provider in (search_google, search_bing, search_duckduckgo, search_yahoo):
        try:
            rows = provider(query, timeout, user_agent, max_results)
            if rows:
                return rows
        except requests.RequestException as exc:
            failures.append(exc)
    if failures:
        raise requests.RequestException("No public search provider available") from failures[-1]
    return []
