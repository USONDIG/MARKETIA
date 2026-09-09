from __future__ import annotations

from typing import Any

import requests

from utils import flatten_record, now_iso, stable_id


def _cpv_codes(config: dict) -> list[str]:
    codes: list[str] = []
    for market in config.get("markets", {}).values():
        if market.get("enabled", True):
            codes.extend(str(c) for c in market.get("cpv", []))
    return sorted(set(codes))


def _query_variants(codes: list[str]) -> list[str]:
    quoted = ", ".join(f'"{c}"' for c in codes)
    plain = ", ".join(codes)
    return [
        f"classification-cpv IN ({quoted})",
        f"classification-cpv IN ({plain})",
        " OR ".join(f'classification-cpv = "{c}"' for c in codes),
        " OR ".join(f"classification-cpv = {c}" for c in codes),
    ]


def collect_ted(config: dict) -> list[dict[str, Any]]:
    source_cfg = config["sources"]["ted"]
    if not source_cfg.get("enabled", True):
        return []

    codes = _cpv_codes(config)
    if not codes:
        return []

    timeout = int(config["automation"].get("request_timeout_seconds", 45))
    page_size = min(int(config["automation"].get("page_size", 100)), 250)
    headers = {
        "User-Agent": config["automation"].get("user_agent", "MARKETIA/1.0"),
        "Content-Type": "application/json",
    }
    fields = [
        "publication-number", "publication-date", "notice-title",
        "buyer-name", "buyer-country", "classification-cpv",
        "procedure-identifier", "notice-type"
    ]

    payload = None
    response_data = None
    last_error: Exception | None = None

    for query in _query_variants(codes):
        payload = {
            "query": query,
            "fields": fields,
            "limit": page_size,
            "paginationMode": "PAGE_NUMBER",
            "page": 1,
        }
        try:
            response = requests.post(source_cfg["base_url"], json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            response_data = response.json()
            break
        except requests.RequestException as exc:
            last_error = exc

    if response_data is None:
        raise RuntimeError(f"TED query failed for all supported query variants: {last_error}")

    notices = response_data.get("notices") or response_data.get("results") or []
    events: list[dict[str, Any]] = []

    for notice in notices:
        if not isinstance(notice, dict):
            continue
        publication_number = notice.get("publication-number") or notice.get("publicationNumber")
        title = notice.get("notice-title") or notice.get("title")
        buyer = notice.get("buyer-name") or notice.get("buyerName")
        country = notice.get("buyer-country") or notice.get("buyerCountry")
        event_date = notice.get("publication-date") or notice.get("publicationDate")
        url = None
        links = notice.get("links") or notice.get("urls")
        if isinstance(links, dict):
            url = next((v for v in links.values() if isinstance(v, str)), None)
        elif isinstance(links, list):
            url = next((v for v in links if isinstance(v, str)), None)

        events.append({
            "id": stable_id("TED", notice),
            "siren": None,
            "company_name": str(buyer) if buyer else None,
            "source": "TED",
            "event_type": "public_tender",
            "event_date": str(event_date) if event_date else None,
            "title": str(title) if title else str(publication_number or "TED notice"),
            "content": flatten_record(notice),
            "url": url,
            "country": str(country) if country else None,
            "raw": notice,
            "collected_at": now_iso(),
        })

    return events
