from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any

import pandas as pd

from business_themes import add_business_theme_columns
from database import connect
from qualification import employee_info, naf_division, qualifies_company
from utils import now_iso


COUNTRY_NAMES = {
    "AT": "Autriche", "AUT": "Autriche",
    "BE": "Belgique", "BEL": "Belgique",
    "BG": "Bulgarie", "BGR": "Bulgarie",
    "HR": "Croatie", "HRV": "Croatie",
    "CY": "Chypre", "CYP": "Chypre",
    "CZ": "Tchéquie", "CZE": "Tchéquie",
    "DK": "Danemark", "DNK": "Danemark",
    "EE": "Estonie", "EST": "Estonie",
    "FI": "Finlande", "FIN": "Finlande",
    "FR": "France", "FRA": "France",
    "DE": "Allemagne", "DEU": "Allemagne",
    "GR": "Grèce", "GRC": "Grèce", "EL": "Grèce",
    "HU": "Hongrie", "HUN": "Hongrie",
    "IE": "Irlande", "IRL": "Irlande",
    "IT": "Italie", "ITA": "Italie",
    "LV": "Lettonie", "LVA": "Lettonie",
    "LT": "Lituanie", "LTU": "Lituanie",
    "LU": "Luxembourg", "LUX": "Luxembourg",
    "MT": "Malte", "MLT": "Malte",
    "NL": "Nederland", "NLD": "Nederland", "NDL": "Nederland",
    "PL": "Pologne", "POL": "Pologne",
    "PT": "Portugal", "PRT": "Portugal",
    "RO": "Roumanie", "ROU": "Roumanie",
    "SK": "Slovaquie", "SVK": "Slovaquie",
    "SI": "Slovénie", "SVN": "Slovénie",
    "ES": "Espagne", "ESP": "Espagne",
    "SE": "Suède", "SWE": "Suède",
    "GB": "Royaume-Uni", "GBR": "Royaume-Uni", "UK": "Royaume-Uni",
    "NO": "Norvège", "NOR": "Norvège",
    "CH": "Suisse", "CHE": "Suisse",
    "IS": "Islande", "ISL": "Islande",
    "US": "États-Unis", "USA": "États-Unis",
    "CA": "Canada", "CAN": "Canada",
}


def _priority(score: float) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    if score >= 35:
        return "WATCH"
    return "LOW"


def _country_code(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, (list, tuple)) and parsed:
            raw = str(parsed[0])
        elif isinstance(parsed, str):
            raw = parsed
    except (ValueError, SyntaxError):
        pass
    raw = raw.strip().strip("[](){}'\" ").upper()
    return raw or None


def country_name(value: Any) -> str | None:
    code = _country_code(value)
    if not code:
        return None
    return COUNTRY_NAMES.get(code, code)


def build_discovery(config: dict, limit: int = 1000) -> pd.DataFrame:
    """Build a broad discovery radar without weakening strict qualification."""
    with connect() as db:
        rows = db.execute(
            """
            SELECT e.id AS event_id, e.siren,
                   COALESCE(e.company_name, c.name, 'Unknown') AS company_name,
                   e.event_type, e.event_date, e.source, e.country,
                   e.title, e.url,
                   s.signal_type, s.label, s.strength, s.weight,
                   c.naf, c.city, c.employees, c.sites,
                   c.headquarters_country
            FROM signals s
            JOIN events e ON e.id = s.event_id
            LEFT JOIN companies c ON c.siren = e.siren
            ORDER BY COALESCE(e.event_date, e.collected_at) DESC
            """
        ).fetchall()

    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        name = str(row["company_name"] or "").strip()
        if not name or name.lower() == "unknown":
            continue
        key = str(row["siren"] or f"NAME::{name.lower()}")
        grouped[key].append(row)

    output: list[dict[str, Any]] = []
    for entity_key, entity_rows in grouped.items():
        first = entity_rows[0]
        labels: set[str] = set()
        sources: set[str] = set()
        event_ids: set[str] = set()
        markets: set[str] = set()
        max_contribution = 0.0
        total_signal_power = 0.0
        has_tender = False

        for row in entity_rows:
            contribution = float(row["strength"] or 0) * float(row["weight"] or 0)
            max_contribution = max(max_contribution, contribution)
            total_signal_power += contribution
            if row["label"]:
                labels.add(str(row["label"]))
            if row["source"]:
                sources.add(str(row["source"]))
            event_ids.add(str(row["event_id"]))
            if row["signal_type"] == "market" and row["label"]:
                markets.add(str(row["label"]))
            if row["event_type"] == "public_tender":
                has_tender = True

        score = min(100.0, max_contribution + min(25.0, total_signal_power * 0.12))
        if has_tender:
            score = max(score, 65.0)
        if len(markets) >= 2:
            score = min(100.0, score + 10.0)
        if len(sources) >= 2:
            score = min(100.0, score + 8.0)

        has_siren = bool(first["siren"])
        has_metadata = bool(first["naf"] or first["employees"] or first["headquarters_country"])
        qualified = qualifies_company(first, config) if has_metadata else False
        if qualified:
            status = "QUALIFIED"
        elif has_metadata:
            status = "ENRICHED"
        elif has_siren:
            status = "IDENTIFIED"
        else:
            status = "DISCOVERED"

        employee = employee_info(first["employees"])
        raw_country = first["headquarters_country"] or first["country"]
        code = _country_code(raw_country)
        output.append({
            "discovery_priority": _priority(score),
            "discovery_score": round(score, 1),
            "status": status,
            "qualified_target": bool(qualified),
            "company_name": first["company_name"],
            "siren": first["siren"],
            "naf": first["naf"],
            "naf_division": naf_division(first["naf"]),
            "city": first["city"],
            "employees": first["employees"],
            "employee_min": employee["employee_min"],
            "employee_range": employee["employee_range"],
            "country_code": code,
            "country": country_name(raw_country),
            "event_count": len(event_ids),
            "signal_count": len(entity_rows),
            "source_count": len(sources),
            "sources": ", ".join(sorted(sources)),
            "markets": ", ".join(sorted(markets)),
            "top_signals": ", ".join(sorted(labels)[:8]),
            "latest_event_date": first["event_date"],
            "latest_title": first["title"],
            "latest_url": first["url"],
            "calculated_at": now_iso(),
        })

    output.sort(key=lambda row: (row["discovery_score"], row["signal_count"]), reverse=True)
    discovery = pd.DataFrame(output[:limit])
    return add_business_theme_columns(discovery)
