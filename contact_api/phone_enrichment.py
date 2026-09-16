from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import unicodedata

from search_providers import search_public_web

# Conservative patterns for French/international professional phone numbers.
PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+|00)33\s?(?:\(0\)\s?)?|0)[1-9](?:[\s.\-]?\d{2}){4}(?!\d)"
)


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _format_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0033"):
        digits = digits[4:]
        if digits.startswith("0"):
            digits = digits[1:]
        return "+33" + digits
    if digits.startswith("33") and len(digits) >= 11:
        digits = digits[2:]
        if digits.startswith("0"):
            digits = digits[1:]
        return "+33" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+33" + digits[1:]
    return raw.strip()


def _company_tokens(company: str) -> list[str]:
    ignored = {"france", "europe", "groupe", "group", "sas", "sa", "sasu", "se", "centre", "center"}
    tokens = [token for token in re.findall(r"[a-z0-9]+", _norm(company)) if len(token) >= 3 and token not in ignored]
    return tokens[:3]


def _evidence_matches(contact: dict, company: str, text: str) -> bool:
    norm = _norm(text)
    name = _norm(str(contact.get("full_name") or ""))
    name_tokens = [token for token in re.findall(r"[a-z0-9]+", name) if len(token) >= 3]
    if len(name_tokens) < 2 or not all(token in norm for token in name_tokens[-2:]):
        return False
    company_tokens = _company_tokens(company)
    return bool(company_tokens) and any(token in norm for token in company_tokens)


def _phone_queries(contact: dict, company: str) -> list[str]:
    name = str(contact.get("full_name") or "").strip()
    return [
        f'"{name}" "{company}" téléphone',
        f'"{name}" "{company}" phone contact',
    ]


def _run_phone_query(query: str) -> tuple[str, list[dict], str | None]:
    try:
        rows = search_public_web(query, timeout=5, user_agent="MARKETIA-contact-api/0.6", max_results=5)
        return query, rows, None
    except Exception as exc:
        return query, [], str(exc)


def enrich_contacts_with_public_phones(contacts: list[dict], company: str, max_contacts: int = 4) -> tuple[list[dict], int]:
    """Enrich top contacts with phone numbers only when name + company + phone coexist in public evidence."""
    if not contacts:
        return contacts, 0

    candidates = contacts[:max_contacts]
    jobs: list[tuple[int, str]] = []
    for idx, contact in enumerate(candidates):
        if str(contact.get("professional_phone") or "").strip():
            continue
        for query in _phone_queries(contact, company):
            jobs.append((idx, query))

    if not jobs:
        return contacts, 0

    results_by_contact: dict[int, list[dict]] = {idx: [] for idx, _ in jobs}
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
        futures = {executor.submit(_run_phone_query, query): (idx, query) for idx, query in jobs}
        for future in as_completed(futures):
            idx, _ = futures[future]
            _, rows, _ = future.result()
            results_by_contact.setdefault(idx, []).extend(rows)

    for idx, result_rows in results_by_contact.items():
        contact = contacts[idx]
        for result in result_rows:
            evidence = " ".join([
                str(result.get("title") or ""),
                str(result.get("snippet") or ""),
            ]).strip()
            if not _evidence_matches(contact, company, evidence):
                continue
            match = PHONE_RE.search(evidence)
            if not match:
                continue
            contact["professional_phone"] = _format_phone(match.group(0))
            contact["phone_status"] = "PUBLIC_PROFESSIONAL_EVIDENCE"
            contact["phone_type"] = "PUBLIC_PROFESSIONAL_UNKNOWN"
            contact["phone_source_name"] = str(result.get("provider") or "serper")
            contact["phone_source_url"] = str(result.get("url") or "")
            contact["phone_evidence"] = evidence[:500]
            break

    return contacts, len(jobs)
