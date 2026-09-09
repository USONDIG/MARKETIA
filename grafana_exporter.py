from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from database import connect
from discovery import build_discovery
from qualification import employee_info, naf_division

OUTPUT_DIR = Path("output")
GRAFANA_DIR = OUTPUT_DIR / "grafana"
HISTORY_DIR = OUTPUT_DIR / "history"


def _query(sql: str) -> pd.DataFrame:
    with connect() as db:
        return pd.read_sql_query(sql, db)


def _records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    clean = df.where(pd.notnull(df), None)
    return clean.to_dict(orient="records")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _prune_history(retention_days: int) -> None:
    if retention_days <= 0 or not HISTORY_DIR.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    for path in HISTORY_DIR.iterdir():
        if not path.is_dir():
            continue
        try:
            stamp = datetime.strptime(path.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if stamp < cutoff:
            shutil.rmtree(path, ignore_errors=True)


def _add_qualification_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["naf_division"] = df["naf"].apply(naf_division)
    df["employee_min"] = df["employees"].apply(lambda value: employee_info(value)["employee_min"])
    df["employee_range"] = df["employees"].apply(lambda value: employee_info(value)["employee_range"])
    df["qualified_target"] = True
    return df


def export_grafana_and_history(config: dict) -> None:
    grafana_cfg = config.get("grafana", {})
    if not grafana_cfg.get("enabled", True):
        return

    top_n = int(grafana_cfg.get("top_opportunities", 500))
    discovery_n = int(grafana_cfg.get("top_discovery", 1000))
    event_limit = int(grafana_cfg.get("recent_events", 2500))
    signal_limit = int(grafana_cfg.get("recent_signals", 5000))

    opportunities = _query(f"""
        SELECT s.priority, s.opportunity_score, s.infra_fit, s.buying_intent,
               s.timing, s.company_name, s.siren, c.naf, c.city, c.employees,
               c.sites, c.headquarters_country AS country, s.top_signal,
               s.calculated_at
        FROM scores s
        LEFT JOIN companies c ON c.siren = s.siren
        ORDER BY s.opportunity_score DESC
        LIMIT {top_n}
    """)
    opportunities = _add_qualification_columns(opportunities)
    discovery = build_discovery(config, limit=discovery_n)

    qualified_sirens = set(opportunities["siren"].dropna().astype(str)) if not opportunities.empty else set()

    events = _query(f"""
        SELECT e.event_date, e.source, e.event_type, e.company_name, e.siren,
               e.country, e.title, e.url, e.collected_at,
               GROUP_CONCAT(DISTINCT s.label) AS detected_signals
        FROM events e
        LEFT JOIN signals s ON s.event_id = e.id
        GROUP BY e.id
        ORDER BY COALESCE(e.event_date, e.collected_at) DESC
        LIMIT {event_limit}
    """)
    qualified_events = events.copy()
    if qualified_sirens and not qualified_events.empty:
        qualified_events = qualified_events[qualified_events["siren"].astype(str).isin(qualified_sirens)]
    else:
        qualified_events = qualified_events.iloc[0:0]

    signals = _query(f"""
        SELECT e.company_name, e.siren, e.source, e.country, e.event_date,
               s.signal_type, s.label, s.strength, s.weight, s.matched_terms,
               e.title, e.url, s.detected_at
        FROM signals s
        JOIN events e ON e.id = s.event_id
        ORDER BY s.detected_at DESC
        LIMIT {signal_limit}
    """)
    qualified_signals = signals.copy()
    if qualified_sirens and not qualified_signals.empty:
        qualified_signals = qualified_signals[qualified_signals["siren"].astype(str).isin(qualified_sirens)]
    else:
        qualified_signals = qualified_signals.iloc[0:0]

    runs = _query("SELECT * FROM runs ORDER BY source")

    priority_summary = opportunities.groupby("priority", dropna=False).size().reset_index(name="count") if not opportunities.empty else pd.DataFrame(columns=["priority", "count"])
    source_summary = qualified_events.groupby("source", dropna=False).size().reset_index(name="count") if not qualified_events.empty else pd.DataFrame(columns=["source", "count"])
    country_summary = opportunities.groupby("country", dropna=False).agg(opportunities=("company_name", "count"), avg_score=("opportunity_score", "mean"), max_score=("opportunity_score", "max")).reset_index() if not opportunities.empty else pd.DataFrame(columns=["country", "opportunities", "avg_score", "max_score"])
    market_summary = qualified_signals[qualified_signals["signal_type"].isin(["market", "job", "web_expansion", "web_tech"])].groupby("label", dropna=False).size().reset_index(name="count") if not qualified_signals.empty else pd.DataFrame(columns=["label", "count"])
    discovery_status_summary = discovery.groupby("status", dropna=False).size().reset_index(name="count") if not discovery.empty else pd.DataFrame(columns=["status", "count"])
    discovery_source_summary = discovery.assign(source=discovery["sources"].fillna("Unknown")).groupby("source", dropna=False).size().reset_index(name="count") if not discovery.empty else pd.DataFrame(columns=["source", "count"])

    now = datetime.now(timezone.utc).replace(microsecond=0)
    stats = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "target_rule": "Industry + commerce + services + public administration, FR, 50+ salaries",
        "discovery_entities": int(len(discovery)),
        "discovery_high": int((discovery["discovery_priority"] == "HIGH").sum()) if not discovery.empty else 0,
        "discovery_medium": int((discovery["discovery_priority"] == "MEDIUM").sum()) if not discovery.empty else 0,
        "identified_or_better": int(discovery["status"].isin(["IDENTIFIED", "ENRICHED", "QUALIFIED"]).sum()) if not discovery.empty else 0,
        "qualified_from_discovery": int((discovery["status"] == "QUALIFIED").sum()) if not discovery.empty else 0,
        "opportunities": int(len(opportunities)),
        "critical": int((opportunities["priority"] == "CRITICAL").sum()) if not opportunities.empty else 0,
        "hot": int((opportunities["priority"] == "HOT").sum()) if not opportunities.empty else 0,
        "warm": int((opportunities["priority"] == "WARM").sum()) if not opportunities.empty else 0,
        "avg_score": round(float(opportunities["opportunity_score"].mean()), 2) if not opportunities.empty else 0,
        "events": int(len(events)),
        "signals": int(len(signals)),
    }

    GRAFANA_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(GRAFANA_DIR / "discovery.json", _records(discovery))
    _write_json(GRAFANA_DIR / "opportunities.json", _records(opportunities))
    _write_json(GRAFANA_DIR / "events.json", _records(events))
    _write_json(GRAFANA_DIR / "qualified_events.json", _records(qualified_events))
    _write_json(GRAFANA_DIR / "signals.json", _records(signals))
    _write_json(GRAFANA_DIR / "qualified_signals.json", _records(qualified_signals))
    _write_json(GRAFANA_DIR / "runs.json", _records(runs))
    _write_json(GRAFANA_DIR / "priority_summary.json", _records(priority_summary))
    _write_json(GRAFANA_DIR / "source_summary.json", _records(source_summary))
    _write_json(GRAFANA_DIR / "country_summary.json", _records(country_summary))
    _write_json(GRAFANA_DIR / "market_summary.json", _records(market_summary))
    _write_json(GRAFANA_DIR / "discovery_status_summary.json", _records(discovery_status_summary))
    _write_json(GRAFANA_DIR / "discovery_source_summary.json", _records(discovery_source_summary))
    _write_json(GRAFANA_DIR / "dashboard_stats.json", [stats])

    history_cfg = config.get("history", {})
    if history_cfg.get("enabled", True):
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        target = HISTORY_DIR / stamp
        target.mkdir(parents=True, exist_ok=True)
        for src in [OUTPUT_DIR / "alerts.csv", OUTPUT_DIR / "server_infra_radar.xlsx"]:
            if src.exists() and (src.suffix != ".xlsx" or history_cfg.get("archive_excel", True)):
                shutil.copy2(src, target / src.name)
        shutil.copytree(GRAFANA_DIR, target / "grafana", dirs_exist_ok=True)
        _write_json(target / "metadata.json", stats)
        _prune_history(int(history_cfg.get("retention_days", 30)))
