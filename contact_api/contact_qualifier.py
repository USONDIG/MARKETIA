from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

ROLE_RULES = [
    ("DECISION_MAKER", 98, ["cio", "dsi", "chief information officer", "directeur des systemes d'information", "directeur des systèmes d'information", "it director", "directeur informatique"]),
    ("TECHNICAL_INFLUENCER", 96, ["infrastructure & cloud director", "infrastructure and cloud director", "infrastructure director", "directeur infrastructure", "head of infrastructure", "cloud director"]),
    ("BUYER", 94, ["it procurement", "procurement it", "acheteur it", "acheteur informatique", "it buyer", "category manager it"]),
    ("TECHNICAL_INFLUENCER", 90, ["infrastructure", "cloud", "datacenter", "data center", "storage", "backup", "network", "réseau", "reseau", "virtualization", "virtualisation", "operations it", "it operations"]),
]

COMPANY_TOKENS = {"xpo", "logistics", "logistique"}
GENERIC_BAD = {"jobs", "job", "careers", "company", "entreprise", "linkedin", "people", "employees", "posts"}


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _linkedin_profile(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = parsed.netloc.casefold()
    return "linkedin.com" in host and parsed.path.startswith("/in/")


def _extract_name(title: str) -> str:
    clean = re.sub(r"\s+", " ", title or "").strip()
    if not clean:
        return ""
    parts = re.split(r"\s+[\-|–|—|•]\s+", clean, maxsplit=1)
    candidate = parts[0].strip()
    candidate = re.sub(r"\s*\|\s*LinkedIn.*$", "", candidate, flags=re.I).strip()
    norm = _norm(candidate)
    if not candidate or len(candidate) > 80:
        return ""
    if any(token in norm.split() for token in GENERIC_BAD):
        return ""
    if any(term in norm for _, _, terms in ROLE_RULES for term in terms):
        return ""
    if len(candidate.split()) < 2:
        return ""
    return candidate


def _best_role(text: str) -> tuple[str, int, str]:
    norm = _norm(text)
    for role_class, score, terms in ROLE_RULES:
        for term in terms:
            if _norm(term) in norm:
                return role_class, score, term
    return "", 0, ""


def qualify_results(company: str, query_rows: list[dict]) -> list[dict]:
    company_norm = _norm(company)
    company_tokens = {tok for tok in re.findall(r"[a-z0-9]+", company_norm) if len(tok) > 2}
    contacts: list[dict] = []
    seen: set[str] = set()

    for query_row in query_rows:
        query = str(query_row.get("query") or "")
        for result in query_row.get("results") or []:
            url = str(result.get("url") or "").strip()
            title = str(result.get("title") or "").strip()
            snippet = str(result.get("snippet") or "").strip()
            if not _linkedin_profile(url):
                continue

            combined = f"{title} {snippet}"
            norm = _norm(combined)
            role_class, base_score, matched_role = _best_role(combined)
            if not role_class:
                continue

            company_match = any(tok in norm for tok in company_tokens) if company_tokens else False
            if not company_match and company_norm not in norm:
                continue

            name = _extract_name(title)
            if not name:
                continue

            canonical = url.split("?", 1)[0].rstrip("/")
            key = canonical.casefold()
            if key in seen:
                continue
            seen.add(key)

            score = min(99, base_score + (2 if company_match else 0))
            job_title = title
            parts = re.split(r"\s+[\-|–|—|•]\s+", title, maxsplit=2)
            if len(parts) >= 2:
                job_title = parts[1].strip()

            contacts.append({
                "company_name": company,
                "full_name": name,
                "job_title": job_title,
                "role_class": role_class,
                "relevance_score": score,
                "linkedin_url": canonical,
                "professional_email": None,
                "professional_phone": None,
                "source_name": str(result.get("provider") or "web_search"),
                "source_url": canonical,
                "confidence": score,
                "status": "PUBLIC_EVIDENCE",
                "role_evidence": matched_role,
                "linkedin_status": "FOUND",
                "email_status": "NOT_FOUND",
                "phone_status": "NOT_FOUND",
                "evidence_summary": snippet[:500],
                "search_query": query,
            })

    contacts.sort(key=lambda row: (-int(row.get("relevance_score") or 0), row.get("full_name") or ""))
    return contacts
