from __future__ import annotations

import html
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from contact_database import upsert_contact
from contacts import build_contact_targets
from utils import now_iso

SEARCH_URL = "https://html.duckduckgo.com/html/"
BLOCKED_DOMAINS = {"linkedin.com", "www.linkedin.com"}

ROLE_PATTERNS = {
    "BUYER": ["procurement", "purchasing", "buyer", "achats", "category manager"],
    "DECISION_MAKER": ["cio", "cto", "dsi", "it director", "directeur informatique", "head of infrastructure"],
    "TECHNICAL_INFLUENCER": [
        "infrastructure", "datacenter", "data center", "systems", "storage", "backup", "network",
        "cloud", "platform", "hpc", "mlops", "ai infrastructure", "virtualization", "operations",
    ],
}

NAME_RE = re.compile(
    r"\b([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’-]+){1,3})\b"
)
TAG_RE = re.compile(r"<[^>]+>")
RESULT_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.I | re.S,
)
SNIPPET_RE = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.I | re.S)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else url
    return html.unescape(url)


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().split(":")[0]


def _is_blocked(url: str) -> bool:
    domain = _domain(url)
    return domain in BLOCKED_DOMAINS or domain.endswith(".linkedin.com")


def _role_matches(text: str, target_title: str, role_class: str) -> bool:
    haystack = text.lower()
    title_tokens = [token for token in re.split(r"[^a-zA-ZÀ-ÿ]+", target_title.lower()) if len(token) >= 4]
    if any(token in haystack for token in title_tokens):
        return True
    return any(token in haystack for token in ROLE_PATTERNS.get(role_class, []))


def _extract_name(title: str, snippet: str, company_name: str, target_title: str) -> str | None:
    combined = f"{title} {snippet}"
    exclusions = {part.lower() for part in re.split(r"\W+", company_name) if part}
    exclusions.update(part.lower() for part in re.split(r"\W+", target_title) if part)
    for candidate in NAME_RE.findall(combined):
        words = candidate.split()
        lowered = {word.lower().strip(".,") for word in words}
        if lowered & exclusions:
            continue
        if any(word.lower() in {"director", "manager", "head", "chief", "responsable", "directeur"} for word in words):
            continue
        return candidate.strip()
    return None


def _guess_job_title(text: str, target_title: str) -> str:
    lower = text.lower()
    if target_title.lower() in lower:
        return target_title
    return target_title


def _search(query: str, timeout: int, user_agent: str, max_results: int) -> list[dict[str, str]]:
    response = requests.get(
        SEARCH_URL,
        params={"q": query},
        headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"},
        timeout=timeout,
    )
    response.raise_for_status()
    anchors = RESULT_RE.findall(response.text)
    snippets = SNIPPET_RE.findall(response.text)
    results: list[dict[str, str]] = []
    for idx, (raw_url, raw_title) in enumerate(anchors[:max_results]):
        url = _unwrap_duckduckgo_url(raw_url)
        if not url.startswith("http") or _is_blocked(url):
            continue
        results.append({
            "url": url,
            "title": _clean_text(raw_title),
            "snippet": _clean_text(snippets[idx]) if idx < len(snippets) else "",
        })
    return results


def discover_contacts(config: dict) -> dict[str, int]:
    settings = config.get("contacts", {})
    if not settings.get("enabled", True) or not settings.get("search_enabled", True):
        return {"queries": 0, "found": 0, "saved": 0}

    max_companies = int(settings.get("search_max_companies", 25))
    roles_per_company = int(settings.get("search_roles_per_company", 6))
    results_per_query = int(settings.get("search_results_per_query", 5))
    timeout = int(settings.get("search_timeout_seconds", 12))
    delay = float(settings.get("search_delay_seconds", 0.35))
    user_agent = str(config.get("automation", {}).get("user_agent", "MARKETIA/1.0 public-contact-discovery"))

    targets = build_contact_targets(limit=max_companies)
    if targets.empty:
        return {"queries": 0, "found": 0, "saved": 0}

    queries = found = saved = 0
    seen_companies: dict[str, int] = {}
    seen_contacts: set[tuple[str, str, str]] = set()

    for row in targets.to_dict(orient="records"):
        entity_key = str(row.get("entity_key") or "")
        company_name = str(row.get("company_name") or "").strip()
        target_title = str(row.get("target_title") or "").strip()
        role_class = str(row.get("role_class") or "").strip()
        if not entity_key or not company_name or not target_title:
            continue

        count = seen_companies.get(entity_key, 0)
        if count >= roles_per_company:
            continue
        seen_companies[entity_key] = count + 1

        query = f'"{company_name}" "{target_title}"'
        queries += 1
        try:
            results = _search(query, timeout=timeout, user_agent=user_agent, max_results=results_per_query)
        except requests.RequestException as exc:
            print(f"[contacts] search warning company={company_name!r} role={target_title!r}: {exc}")
            continue

        for result in results:
            evidence = f"{result['title']} {result['snippet']}"
            if company_name.lower() not in evidence.lower():
                # The company name must be visible in the public evidence to reduce false matches.
                continue
            if not _role_matches(evidence, target_title, role_class):
                continue
            full_name = _extract_name(result["title"], result["snippet"], company_name, target_title)
            if not full_name:
                continue

            dedupe = (entity_key, full_name.lower(), target_title.lower())
            if dedupe in seen_contacts:
                continue
            seen_contacts.add(dedupe)
            found += 1

            source_domain = _domain(result["url"])
            confidence = 72.0 if target_title.lower() in evidence.lower() else 58.0
            contact: dict[str, Any] = {
                "entity_key": entity_key,
                "siren": row.get("siren"),
                "company_name": company_name,
                "full_name": full_name,
                "job_title": _guess_job_title(evidence, target_title),
                "role_class": role_class,
                "relevance_score": float(row.get("relevance_score") or 0),
                "linkedin_url": None,
                "professional_email": None,
                "professional_phone": None,
                "source_name": source_domain or "public_web",
                "source_url": result["url"],
                "confidence": confidence,
                "verified_at": now_iso(),
                "status": "PUBLIC_SOURCE_FOUND",
                "raw_json": str({"query": query, "title": result["title"], "snippet": result["snippet"]}),
                "updated_at": now_iso(),
            }
            upsert_contact(contact)
            saved += 1

        time.sleep(max(0.0, delay))

    return {"queries": queries, "found": found, "saved": saved}
