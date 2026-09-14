from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Callable

import requests

from contact_database import upsert_contact
from contact_search import _clean_company_name, _domain, _extract_name, _is_linkedin, _role_matches, _search_targets
from contact_search_providers import search_public_web
from utils import now_iso

TAG_RE = re.compile(r"<[^>]+>")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s().-]*)?(?:\d[\s().-]*){8,14}\d")


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()


def _tokens(value: str) -> list[str]:
    ignored = {"france", "europe", "sas", "sa", "sarl", "groupe", "group", "logistics"}
    return [t.casefold() for t in re.split(r"[^A-Za-zÀ-ÿ0-9'-]+", value) if len(t) >= 3 and t.casefold() not in ignored]


def _mentions(text: str, value: str, require_two: bool = False) -> bool:
    haystack = text.casefold()
    tokens = _tokens(value)
    if not tokens:
        return False
    matches = sum(token in haystack for token in tokens[:4])
    return matches >= (2 if require_two and len(tokens) >= 2 else 1)


def _fetch_public_page(url: str, timeout: int, user_agent: str) -> tuple[str, str]:
    if _is_linkedin(url):
        return "", url
    response = requests.get(
        url,
        headers={"User-Agent": user_agent, "Accept-Language": "fr,en;q=0.8"},
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    if "text/html" not in response.headers.get("Content-Type", "text/html").lower():
        return "", response.url
    return _text(response.text[:1_000_000]), response.url


def _coordinates(text: str) -> tuple[str | None, str | None]:
    emails: list[str] = []
    for value in EMAIL_RE.findall(text):
        lower = value.lower()
        if lower.endswith(("example.com", "domain.com", "sentry.io")):
            continue
        if value not in emails:
            emails.append(value)
    phones: list[str] = []
    for value in PHONE_RE.findall(text):
        compact = re.sub(r"\s+", " ", value).strip(" .,-")
        digits = re.sub(r"\D", "", compact)
        if 9 <= len(digits) <= 15 and compact not in phones:
            phones.append(compact)
    return (emails[0] if emails else None, phones[0] if phones else None)


def enrich_person_coordinates(
    full_name: str,
    company_name: str,
    timeout: int,
    user_agent: str,
    max_results: int,
    search_fn: Callable[..., list[dict[str, str]]] = search_public_web,
) -> dict[str, Any]:
    queries = [
        f'"{full_name}" "{company_name}" email',
        f'"{full_name}" "{company_name}" contact',
        f'"{full_name}" "{company_name}" téléphone',
    ]
    result = {
        "email": None, "phone": None,
        "email_status": "NOT_FOUND", "phone_status": "NOT_FOUND",
        "source_url": None, "source_name": None,
    }
    seen: set[str] = set()
    for query in queries:
        try:
            rows = search_fn(query, timeout=timeout, user_agent=user_agent, max_results=max_results)
        except requests.RequestException:
            continue
        for row in rows:
            url = str(row.get("url") or "")
            if not url or url in seen or _is_linkedin(url):
                continue
            seen.add(url)
            try:
                page_text, final_url = _fetch_public_page(url, timeout, user_agent)
            except requests.RequestException:
                continue
            evidence = f"{row.get('title', '')} {row.get('snippet', '')} {page_text}"
            if not _mentions(evidence, full_name, require_two=True) or not _mentions(evidence, company_name):
                continue
            email, phone = _coordinates(page_text)
            if email and not result["email"]:
                result.update(email=email, email_status="CONFIRMED_PUBLIC", source_url=final_url, source_name=_domain(final_url))
            if phone and not result["phone"]:
                result["phone"] = phone
                result["phone_status"] = "CONFIRMED_PUBLIC"
                result["source_url"] = result["source_url"] or final_url
                result["source_name"] = result["source_name"] or _domain(final_url)
            if result["email"] and result["phone"]:
                return result
    return result


def discover_contacts(config: dict) -> dict[str, int]:
    settings = config.get("contacts", {})
    if not settings.get("enabled", True) or not settings.get("search_enabled", True):
        return {"queries": 0, "found": 0, "saved": 0, "linkedin": 0, "coordinates": 0}

    max_companies = int(settings.get("search_max_companies", 12))
    roles_per_company = int(settings.get("search_roles_per_company", 3))
    results_per_query = int(settings.get("search_results_per_query", 5))
    timeout = max(2, min(10, int(settings.get("search_timeout_seconds", 6))))
    max_runtime = max(45, int(settings.get("search_max_runtime_seconds", 240)))
    user_agent = str(config.get("automation", {}).get("user_agent", "MARKETIA/2.0 public-contact-intelligence"))

    targets = _search_targets(config, max_companies)
    queries = found = saved = linkedin_found = coordinates_found = 0
    per_company: dict[str, int] = {}
    seen_people: set[tuple[str, str]] = set()
    started = time.monotonic()

    for row in targets:
        if time.monotonic() - started >= max_runtime:
            break
        entity_key = str(row.get("entity_key") or "")
        company_name = _clean_company_name(row.get("company_name"))
        target_title = str(row.get("target_title") or "").strip()
        role_class = str(row.get("role_class") or "").strip()
        if not entity_key or not company_name or not target_title:
            continue
        if per_company.get(entity_key, 0) >= roles_per_company:
            continue
        per_company[entity_key] = per_company.get(entity_key, 0) + 1

        candidate_queries = [
            f'site:linkedin.com/in "{company_name}" "{target_title}"',
            f'"{company_name}" "{target_title}" LinkedIn',
            f'"{company_name}" "{target_title}"',
        ]
        candidates: list[dict[str, str]] = []
        for query in candidate_queries:
            queries += 1
            try:
                candidates.extend(search_public_web(query, timeout, user_agent, results_per_query))
            except requests.RequestException as exc:
                print(f"[contacts-v2] search warning {company_name!r}: {exc}")

        candidates.sort(key=lambda item: 0 if _is_linkedin(str(item.get("url") or "")) else 1)
        seen_urls: set[str] = set()
        for candidate in candidates:
            url = str(candidate.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            evidence = f"{candidate.get('title', '')} {candidate.get('snippet', '')}"
            if not _mentions(evidence, company_name) or not _role_matches(evidence, target_title, role_class):
                continue
            full_name = _extract_name(str(candidate.get("title") or ""), str(candidate.get("snippet") or ""), company_name, target_title)
            if not full_name:
                continue
            person_key = (entity_key, full_name.casefold())
            if person_key in seen_people:
                continue
            seen_people.add(person_key)
            found += 1

            linkedin_url = url if _is_linkedin(url) else None
            if linkedin_url:
                linkedin_found += 1
            enriched = enrich_person_coordinates(full_name, company_name, timeout, user_agent, results_per_query)
            if enriched["email"] or enriched["phone"]:
                coordinates_found += 1

            exact_role = target_title.casefold() in evidence.casefold()
            role_evidence = "CONFIRMED_EXACT" if exact_role else "CONFIRMED_ROLE_FAMILY"
            confidence = 82.0 if linkedin_url and exact_role else 74.0 if linkedin_url else 66.0
            if enriched["email"]:
                confidence += 8.0
            if enriched["phone"]:
                confidence += 4.0

            contact: dict[str, Any] = {
                "entity_key": entity_key,
                "siren": row.get("siren"),
                "company_name": company_name,
                "full_name": full_name,
                "job_title": target_title,
                "role_class": role_class,
                "relevance_score": float(row.get("relevance_score") or 0),
                "linkedin_url": linkedin_url,
                "professional_email": enriched["email"],
                "professional_phone": enriched["phone"],
                "source_name": enriched["source_name"] or ("LinkedIn public search" if linkedin_url else (_domain(url) or "public_web")),
                "source_url": enriched["source_url"] or url,
                "confidence": min(98.0, confidence),
                "verified_at": now_iso(),
                "status": "CONTACT_WITH_COORDINATES" if (enriched["email"] or enriched["phone"]) else "CONTACT_CONFIRMED",
                "role_evidence": role_evidence,
                "linkedin_status": "CONFIRMED_PUBLIC_SEARCH" if linkedin_url else "NOT_FOUND",
                "email_status": enriched["email_status"],
                "phone_status": enriched["phone_status"],
                "evidence_summary": ", ".join(filter(None, [role_evidence, "LINKEDIN_PUBLIC_SEARCH" if linkedin_url else "", "EMAIL_PUBLIC" if enriched["email"] else "", "PHONE_PUBLIC" if enriched["phone"] else ""])),
                "raw_json": json.dumps({"candidate_queries": candidate_queries, "title": candidate.get("title"), "snippet": candidate.get("snippet"), "coordinate_source": enriched["source_url"]}, ensure_ascii=False),
                "updated_at": now_iso(),
            }
            upsert_contact(contact)
            saved += 1
            break

    return {"queries": queries, "found": found, "saved": saved, "linkedin": linkedin_found, "coordinates": coordinates_found}
