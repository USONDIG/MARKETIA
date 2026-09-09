from __future__ import annotations

import html
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from contact_database import upsert_contact
from contacts import build_contact_targets
from discovery import build_discovery
from utils import now_iso

SEARCH_URL = "https://html.duckduckgo.com/html/"
LINKEDIN_DOMAINS = {"linkedin.com", "www.linkedin.com"}

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
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s().-]*)?(?:\d[\s().-]*){8,14}\d")


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


def _is_linkedin(url: str) -> bool:
    domain = _domain(url)
    return domain in LINKEDIN_DOMAINS or domain.endswith(".linkedin.com")


def _role_class_for_title(title: str) -> str:
    text = title.lower()
    if any(token in text for token in ["procurement", "buyer", "achats", "category manager", "purchasing"]):
        return "BUYER"
    if any(token in text for token in ["cio", "cto", "dsi", "it director", "directeur informatique"]):
        return "DECISION_MAKER"
    return "TECHNICAL_INFLUENCER"


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
    exclusions.update({"linkedin", "profil", "profile", "france"})
    for candidate in NAME_RE.findall(combined):
        words = candidate.split()
        lowered = {word.lower().strip(".,") for word in words}
        if lowered & exclusions:
            continue
        if any(word.lower() in {"director", "manager", "head", "chief", "responsable", "directeur"} for word in words):
            continue
        return candidate.strip()
    return None


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
        if not url.startswith("http"):
            continue
        results.append({
            "url": url,
            "title": _clean_text(raw_title),
            "snippet": _clean_text(snippets[idx]) if idx < len(snippets) else "",
        })
    return results


def _public_coordinates(url: str, timeout: int, user_agent: str) -> tuple[str | None, str | None]:
    # LinkedIn pages are deliberately not crawled. We only retain the public
    # profile URL and search-result evidence exposed by the search engine.
    if _is_linkedin(url):
        return None, None
    try:
        response = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return None, None
    if "text/html" not in response.headers.get("Content-Type", "text/html").lower():
        return None, None
    text = html.unescape(response.text[:1_000_000])
    emails = [value for value in EMAIL_RE.findall(text) if not value.lower().endswith(("example.com", "domain.com"))]
    phones = [re.sub(r"\s+", " ", value).strip() for value in PHONE_RE.findall(_clean_text(text))]
    return (emails[0] if emails else None, phones[0] if phones else None)


def _search_targets(config: dict, max_companies: int) -> list[dict[str, Any]]:
    qualified = build_contact_targets(limit=max_companies)
    rows = qualified.to_dict(orient="records") if not qualified.empty else []
    known_entities = {str(row.get("entity_key") or "") for row in rows}

    discovery = build_discovery(config, limit=max(max_companies * 4, 100))
    if discovery.empty:
        return rows

    selected_companies = set(known_entities)
    for lead in discovery.to_dict(orient="records"):
        priority = str(lead.get("discovery_priority") or "")
        if priority not in {"HIGH", "MEDIUM"}:
            continue
        company_name = str(lead.get("company_name") or "").strip()
        if not company_name:
            continue
        siren = str(lead.get("siren") or "").strip()
        entity_key = siren or f"NAME::{company_name.lower()}"
        if entity_key not in selected_companies and len(selected_companies) >= max_companies:
            continue
        selected_companies.add(entity_key)
        if entity_key in known_entities:
            continue

        role_text = str(lead.get("likely_contact_roles") or "")
        titles = [part.strip() for part in role_text.split(",") if part.strip()]
        for title in titles:
            rows.append({
                "entity_key": entity_key,
                "siren": lead.get("siren"),
                "company_name": company_name,
                "opportunity_score": lead.get("discovery_score"),
                "priority": priority,
                "role_class": _role_class_for_title(title),
                "target_title": title,
                "relevance_score": 80,
                "markets": lead.get("markets"),
                "preferred_sources": "LinkedIn public search, site corporate, communiqués, conférences/speakers",
            })
    return rows


def discover_contacts(config: dict) -> dict[str, int]:
    settings = config.get("contacts", {})
    if not settings.get("enabled", True) or not settings.get("search_enabled", True):
        return {"queries": 0, "found": 0, "saved": 0, "linkedin": 0}

    max_companies = int(settings.get("search_max_companies", 25))
    roles_per_company = int(settings.get("search_roles_per_company", 6))
    results_per_query = int(settings.get("search_results_per_query", 5))
    timeout = int(settings.get("search_timeout_seconds", 12))
    delay = float(settings.get("search_delay_seconds", 0.35))
    user_agent = str(config.get("automation", {}).get("user_agent", "MARKETIA/1.0 public-contact-discovery"))

    targets = _search_targets(config, max_companies)
    if not targets:
        return {"queries": 0, "found": 0, "saved": 0, "linkedin": 0}

    queries = found = saved = linkedin_found = 0
    seen_companies: dict[str, int] = {}
    seen_contacts: set[tuple[str, str, str]] = set()

    for row in targets:
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

        search_queries = [
            f'"{company_name}" "{target_title}"',
            f'site:linkedin.com/in "{company_name}" "{target_title}"',
        ]

        results: list[dict[str, str]] = []
        for query in search_queries:
            queries += 1
            try:
                results.extend(_search(query, timeout=timeout, user_agent=user_agent, max_results=results_per_query))
            except requests.RequestException as exc:
                print(f"[contacts] search warning company={company_name!r} role={target_title!r}: {exc}")
            time.sleep(max(0.0, delay))

        seen_urls: set[str] = set()
        for result in results:
            if result["url"] in seen_urls:
                continue
            seen_urls.add(result["url"])
            evidence = f"{result['title']} {result['snippet']}"
            if company_name.lower() not in evidence.lower():
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

            is_linkedin = _is_linkedin(result["url"])
            professional_email, professional_phone = _public_coordinates(result["url"], timeout, user_agent)
            source_domain = _domain(result["url"])
            exact_role = target_title.lower() in evidence.lower()
            if is_linkedin:
                linkedin_found += 1
                confidence = 76.0 if exact_role else 64.0
                source_name = "LinkedIn public search"
                status = "LINKEDIN_PROFILE_FOUND"
            else:
                confidence = 78.0 if exact_role and (professional_email or professional_phone) else (72.0 if exact_role else 58.0)
                source_name = source_domain or "public_web"
                status = "PUBLIC_SOURCE_FOUND"

            contact: dict[str, Any] = {
                "entity_key": entity_key,
                "siren": row.get("siren"),
                "company_name": company_name,
                "full_name": full_name,
                "job_title": target_title,
                "role_class": role_class,
                "relevance_score": float(row.get("relevance_score") or 0),
                "linkedin_url": result["url"] if is_linkedin else None,
                "professional_email": professional_email,
                "professional_phone": professional_phone,
                "source_name": source_name,
                "source_url": result["url"],
                "confidence": confidence,
                "verified_at": now_iso(),
                "status": status,
                "raw_json": str({"query": search_queries, "title": result["title"], "snippet": result["snippet"]}),
                "updated_at": now_iso(),
            }
            upsert_contact(contact)
            saved += 1

    return {"queries": queries, "found": found, "saved": saved, "linkedin": linkedin_found}
