from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from utils import normalize_text, now_iso


def _days_old(date_value: str | None) -> int | None:
    if not date_value:
        return None
    raw = str(date_value).replace("Z", "+00:00")
    for candidate in (raw, raw[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dt).days)
        except ValueError:
            continue
    return None


def freshness_strength(days: int | None) -> float:
    if days is None:
        return 0.5
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.75
    if days <= 90:
        return 0.45
    if days <= 180:
        return 0.2
    return 0.05


def _matched(text: str, terms: list[str]) -> list[str]:
    normalized = normalize_text(text)
    return [term for term in terms if normalize_text(term) in normalized]


def detect_signals(event: dict[str, Any], config: dict) -> list[dict[str, Any]]:
    text = " ".join(filter(None, [event.get("title"), event.get("content"), event.get("company_name")]))
    signals: list[dict[str, Any]] = []
    detected_at = now_iso()

    for sector in config.get("sectors", []):
        if not sector.get("enabled", True):
            continue
        matches = _matched(text, sector.get("keywords", []))
        if matches:
            signals.append({
                "siren": event.get("siren"),
                "signal_type": "sector",
                "label": sector.get("label") or sector["id"],
                "strength": min(1.0, 0.5 + 0.15 * len(matches)),
                "weight": float(sector.get("weight", 0)),
                "matched_terms": matches,
                "detected_at": detected_at,
            })

    for market_id, market in config.get("markets", {}).items():
        if not market.get("enabled", True):
            continue
        matches = _matched(text, market.get("keywords", []))
        cpv_matches = []
        raw = normalize_text(event.get("raw", {}))
        for cpv in market.get("cpv", []):
            if str(cpv) in raw:
                cpv_matches.append(str(cpv))
        all_matches = matches + cpv_matches
        if all_matches:
            base_strength = min(1.0, 0.55 + 0.12 * len(all_matches))
            if event.get("event_type") == "public_tender":
                base_strength = min(1.0, base_strength + 0.2)
            signals.append({
                "siren": event.get("siren"),
                "signal_type": "market",
                "label": market.get("label") or market_id,
                "strength": base_strength,
                "weight": float(market.get("weight", 0)),
                "matched_terms": all_matches,
                "detected_at": detected_at,
            })

    if event.get("event_type") == "job_posting" and config.get("job_signals", {}).get("enabled", True):
        matches = _matched(text, config.get("job_signals", {}).get("keywords", []))
        if matches:
            signals.append({
                "siren": event.get("siren"),
                "signal_type": "market",
                "label": "Recrutement Infrastructure / IA",
                "strength": min(1.0, 0.7 + 0.08 * len(matches)),
                "weight": float(config.get("job_signals", {}).get("weight", 18)),
                "matched_terms": matches,
                "detected_at": detected_at,
            })
            signals.append({
                "siren": event.get("siren"),
                "signal_type": "timing",
                "label": "Recrutement technique recent",
                "strength": freshness_strength(_days_old(event.get("event_date"))),
                "weight": float(config.get("job_signals", {}).get("timing_weight", 18)),
                "matched_terms": matches,
                "detected_at": detected_at,
            })

    if event.get("event_type") == "web_news":
        web_cfg = config.get("web_signals", {})
        expansion_matches = _matched(text, web_cfg.get("expansion_keywords", []))
        tech_matches = _matched(text, web_cfg.get("tech_keywords", []))
        if expansion_matches:
            signals.append({
                "siren": event.get("siren"),
                "signal_type": "timing",
                "label": "Expansion / investissement",
                "strength": min(1.0, 0.65 + 0.08 * len(expansion_matches)),
                "weight": float(web_cfg.get("expansion_weight", 20)),
                "matched_terms": expansion_matches,
                "detected_at": detected_at,
            })
        if tech_matches:
            signals.append({
                "siren": event.get("siren"),
                "signal_type": "market",
                "label": "Projet technologique public",
                "strength": min(1.0, 0.6 + 0.08 * len(tech_matches)),
                "weight": float(web_cfg.get("tech_weight", 20)),
                "matched_terms": tech_matches,
                "detected_at": detected_at,
            })

    if event.get("event_type") == "public_tender":
        days = _days_old(event.get("event_date"))
        signals.append({
            "siren": event.get("siren"),
            "signal_type": "timing",
            "label": "Appel d'offres recent",
            "strength": freshness_strength(days),
            "weight": float(config.get("scoring", {}).get("recent_tender_bonus", 30)),
            "matched_terms": [event.get("source", "tender")],
            "detected_at": detected_at,
        })

    if event.get("event_type") == "company_event":
        days = _days_old(event.get("event_date"))
        signals.append({
            "siren": event.get("siren"),
            "signal_type": "timing",
            "label": "Evenement entreprise recent",
            "strength": freshness_strength(days),
            "weight": float(config.get("scoring", {}).get("recent_company_event_bonus", 12)),
            "matched_terms": [event.get("source", "company_event")],
            "detected_at": detected_at,
        })

    return signals
