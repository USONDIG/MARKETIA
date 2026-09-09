from __future__ import annotations

from typing import Any

import requests

from utils import first_value, flatten_record, now_iso, stable_id, extract_siren


def _headers(config: dict) -> dict[str, str]:
    return {"User-Agent": config["automation"].get("user_agent", "MARKETIA/1.0")}


def collect_ods(source_name: str, config: dict) -> list[dict[str, Any]]:
    source_cfg = config["sources"][source_name]
    if not source_cfg.get("enabled", True):
        return []

    base_url = source_cfg["base_url"]
    page_size = int(config["automation"].get("page_size", 100))
    max_pages = int(config["automation"].get("max_pages_per_source", 10))
    timeout = int(config["automation"].get("request_timeout_seconds", 45))

    events: list[dict[str, Any]] = []
    for page in range(max_pages):
        params = {"limit": page_size, "offset": page * page_size}
        response = requests.get(base_url, params=params, headers=_headers(config), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("results", [])
        if not records:
            break

        for record in records:
            text = flatten_record(record)
            company_name = first_value(record, [
                "nom_entreprise", "denomination", "denominationunitelegale",
                "titulaire", "acheteur", "buyer", "nom"
            ])
            siren = extract_siren(str(first_value(record, [
                "siren", "siren_acheteur", "siren_titulaire", "identifiant"
            ]) or ""))
            date_value = first_value(record, [
                "dateparution", "date_publication", "datepublication",
                "date", "publication_date"
            ])
            title = first_value(record, [
                "objet", "title", "titre", "intitule", "annonce"
            ])
            url = first_value(record, ["url", "url_avis", "lien", "link"])

            event_type = "public_tender" if source_name == "boamp" else "company_event"
            events.append({
                "id": stable_id(source_name.upper(), record),
                "siren": siren,
                "company_name": str(company_name) if company_name else None,
                "source": source_name.upper(),
                "event_type": event_type,
                "event_date": str(date_value) if date_value else None,
                "title": str(title) if title else None,
                "content": text,
                "url": str(url) if url else None,
                "country": "FR",
                "raw": record,
                "collected_at": now_iso(),
            })

        if len(records) < page_size:
            break

    return events
