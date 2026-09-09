from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

import requests

from utils import first_value, flatten_record, now_iso, stable_id, extract_siren


def _headers(config: dict) -> dict[str, str]:
    return {"User-Agent": config["automation"].get("user_agent", "MARKETIA/1.0")}


def _discover_records_url(source_name: str, configured_url: str, config: dict) -> str:
    """Discover the current OpenDataSoft dataset id by searching the host catalog.

    This avoids hard-coding a dataset id that may change while keeping the configured
    records URL as a fallback.
    """
    parsed = urlparse(configured_url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    timeout = int(config["automation"].get("request_timeout_seconds", 45))
    headers = _headers(config)

    candidates = [
        f"{host}/api/explore/v2.1/catalog/datasets",
        f"{host}/api/explore/v2.0/catalog/datasets",
    ]

    for catalog_url in candidates:
        try:
            response = requests.get(catalog_url, params={"limit": 100}, headers=headers, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            datasets = payload.get("results") or payload.get("datasets") or []
            for dataset in datasets:
                blob = flatten_record(dataset)
                if source_name.lower() not in blob:
                    continue
                dataset_id = (
                    dataset.get("dataset_id")
                    or dataset.get("datasetid")
                    or dataset.get("id")
                )
                if not dataset_id and isinstance(dataset.get("metas"), dict):
                    dataset_id = dataset["metas"].get("dataset_id") or dataset["metas"].get("datasetid")
                if dataset_id:
                    api_version = "v2.1" if "/v2.1/" in catalog_url else "v2.0"
                    return f"{host}/api/explore/{api_version}/catalog/datasets/{dataset_id}/records"
        except requests.RequestException:
            continue

    return configured_url


def collect_ods(source_name: str, config: dict) -> list[dict[str, Any]]:
    source_cfg = config["sources"][source_name]
    if not source_cfg.get("enabled", True):
        return []

    base_url = _discover_records_url(source_name, source_cfg["base_url"], config)
    page_size = min(int(config["automation"].get("page_size", 100)), 100)
    max_pages = int(config["automation"].get("max_pages_per_source", 10))
    timeout = int(config["automation"].get("request_timeout_seconds", 45))

    events: list[dict[str, Any]] = []
    for page in range(max_pages):
        params = {"limit": page_size, "offset": page * page_size}
        response = requests.get(base_url, params=params, headers=_headers(config), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("results") or payload.get("records") or []
        if not records:
            break

        for record in records:
            if isinstance(record, dict) and isinstance(record.get("record"), dict):
                record = record["record"]
            text = flatten_record(record)
            company_name = first_value(record, [
                "nom_entreprise", "denomination", "denominationunitelegale",
                "titulaire", "acheteur", "buyer", "nom", "nom_raison_sociale"
            ])
            siren = extract_siren(str(first_value(record, [
                "siren", "siren_acheteur", "siren_titulaire", "identifiant",
                "registre", "numero_siren"
            ]) or ""))
            date_value = first_value(record, [
                "dateparution", "date_publication", "datepublication",
                "date", "publication_date", "dateparutionannonce"
            ])
            title = first_value(record, [
                "objet", "title", "titre", "intitule", "annonce", "description"
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

    print(f"[{source_name}] endpoint={base_url}")
    return events
