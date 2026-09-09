from __future__ import annotations

import time
from typing import Any

import requests

from utils import now_iso


def _pick(result: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = result.get(key)
        if value not in (None, "", []):
            return value
    return None


def search_company(query: str, config: dict) -> dict[str, Any] | None:
    if not query or not config["sources"]["recherche_entreprises"].get("enabled", True):
        return None

    base = config["sources"]["recherche_entreprises"]["base_url"].rstrip("/")
    timeout = int(config["automation"].get("request_timeout_seconds", 45))
    headers = {"User-Agent": config["automation"].get("user_agent", "MARKETIA/1.0")}
    response = requests.get(
        f"{base}/search",
        params={"q": query, "per_page": 1},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or payload.get("etablissements") or []
    if not results:
        return None

    result = results[0]
    siren = str(_pick(result, "siren", "siren_unite_legale") or "")
    if len(siren) != 9:
        return None

    siege = result.get("siege") if isinstance(result.get("siege"), dict) else {}
    name_value = _pick(result, "nom_complet", "nom_raison_sociale", "denomination", "nom") or query
    city = _pick(siege, "libelle_commune", "commune", "ville") or _pick(result, "libelle_commune", "ville")
    return {
        "siren": siren,
        "name": str(name_value),
        "naf": _pick(result, "activite_principale", "code_naf"),
        "city": str(city) if city else None,
        "employees": _pick(result, "tranche_effectif_salarie", "tranche_effectif"),
        "sites": _pick(result, "nombre_etablissements_ouverts", "nombre_etablissements"),
        "website": None,
        "headquarters_country": "FR",
        "raw": result,
        "updated_at": now_iso(),
    }


def enrich_events(events: list[dict[str, Any]], config: dict, max_lookups: int = 100) -> dict[str, dict[str, Any]]:
    companies: dict[str, dict[str, Any]] = {}
    seen_queries: set[str] = set()
    lookups = 0

    # Prefer entities already carrying a SIREN (especially BODACC), then company names.
    ordered = sorted(events, key=lambda event: 0 if event.get("siren") else 1)
    for event in ordered:
        if lookups >= max_lookups:
            break
        query = str(event.get("siren") or (event.get("company_name") or "").strip())
        if not query or query.lower() in seen_queries:
            continue
        seen_queries.add(query.lower())
        try:
            company = search_company(query, config)
            lookups += 1
            if company:
                companies[company["siren"]] = company
                if not event.get("siren"):
                    event["siren"] = company["siren"]
            time.sleep(0.16)
        except requests.RequestException:
            continue

    return companies
