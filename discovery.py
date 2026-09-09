from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from database import connect
from qualification import employee_info, naf_division, qualifies_company
from utils import now_iso


def _priority(score: float) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    if score >= 35:
        return "WATCH"
    return "LOW"


def build_discovery(config: dict, limit: int = 1000) -> pd.DataFrame:
    """Build a broad discovery radar without weakening strict qualification.

    Every entity carrying at least one detected signal can appear here, even if
    company metadata is incomplete. Strict qualification is exposed as a status
    and remains enforced separately by the normal scores/opportunities pipeline.
    """
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

        # Broad signal score: intentionally independent from strict qualification.
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
            "country": first["headquarters_country"] or first["country"],
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
    return pd.DataFrame(output[:limit])
