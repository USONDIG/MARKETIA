from __future__ import annotations

from collections import defaultdict
from typing import Any

from database import connect, save_score
from qualification import qualifies_company
from utils import now_iso


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _priority(score: float, config: dict) -> str:
    alerts = config.get("alerts", {})
    if score >= float(alerts.get("critical_score", 90)):
        return "CRITICAL"
    if score >= float(alerts.get("hot_score", 80)):
        return "HOT"
    if score >= float(alerts.get("minimum_score", 65)):
        return "WARM"
    if score >= 45:
        return "WATCH"
    return "LOW"


def calculate_scores(config: dict) -> list[dict[str, Any]]:
    with connect() as db:
        # Rebuild the score table every run so previously-qualified companies
        # disappear as soon as they no longer match the targeting rules.
        db.execute("DELETE FROM scores")
        rows = db.execute(
            """
            SELECT e.id AS event_id, e.siren,
                   COALESCE(e.company_name, c.name, 'Unknown') AS company_name,
                   e.event_type, s.signal_type, s.label, s.strength, s.weight,
                   e.event_date, e.source,
                   c.naf, c.employees, c.headquarters_country
            FROM signals s
            JOIN events e ON e.id = s.event_id
            LEFT JOIN companies c ON c.siren = e.siren
            """
        ).fetchall()

    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        # Strict targeting: only score enriched companies that satisfy the
        # configured service-sector + employee-size rules.
        if not qualifies_company(row, config):
            continue
        entity_key = row["siren"] or f"NAME::{row['company_name']}"
        grouped[entity_key].append(row)

    settings = config.get("scoring", {})
    fit_w = float(settings.get("infra_fit_weight", 0.35))
    intent_w = float(settings.get("buying_intent_weight", 0.45))
    timing_w = float(settings.get("timing_weight", 0.20))
    multi_bonus = float(settings.get("multi_signal_bonus", 10))

    output: list[dict[str, Any]] = []
    for entity_key, entity_rows in grouped.items():
        infra_fit = 0.0
        buying_intent = 0.0
        timing = 0.0
        market_labels: set[str] = set()
        contributions: list[tuple[float, str]] = []
        has_public_tender = False

        for row in entity_rows:
            contribution = float(row["strength"]) * float(row["weight"])
            if row["event_type"] == "public_tender":
                has_public_tender = True
            if row["signal_type"] == "sector":
                infra_fit += contribution
            elif row["signal_type"] == "market":
                buying_intent += contribution
                market_labels.add(row["label"] or "market")
            elif row["signal_type"] == "timing":
                timing += contribution
            contributions.append((contribution, row["label"] or row["signal_type"]))

        if has_public_tender and market_labels:
            infra_fit = max(infra_fit, 55.0)
            buying_intent = max(buying_intent, 78.0)
            timing = max(timing, 82.0)
        if len(market_labels) >= 2:
            buying_intent += multi_bonus
            if has_public_tender:
                buying_intent = max(buying_intent, 88.0)
        if len(market_labels) >= 3 and has_public_tender:
            buying_intent = max(buying_intent, 95.0)
            timing += multi_bonus / 2

        infra_fit = clamp(infra_fit)
        buying_intent = clamp(buying_intent)
        timing = clamp(timing)
        total = clamp(infra_fit * fit_w + buying_intent * intent_w + timing * timing_w)
        top_signal = max(contributions, default=(0, ""), key=lambda x: x[0])[1]
        first = entity_rows[0]

        score = {
            "entity_key": entity_key,
            "siren": first["siren"],
            "company_name": first["company_name"],
            "infra_fit": round(infra_fit, 1),
            "buying_intent": round(buying_intent, 1),
            "timing": round(timing, 1),
            "opportunity_score": round(total, 1),
            "priority": _priority(total, config),
            "top_signal": top_signal,
            "calculated_at": now_iso(),
        }
        save_score(score)
        output.append(score)

    return sorted(output, key=lambda row: row["opportunity_score"], reverse=True)
