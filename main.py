from __future__ import annotations

import traceback
from pathlib import Path

import yaml

from collectors.companies import enrich_events
from collectors.ods import collect_ods
from collectors.public_web import collect_jobs, collect_news
from collectors.ted import collect_ted
from database import (
    init_db,
    insert_event,
    replace_signals_for_event,
    update_run,
    upsert_company,
)
from exporter import export_outputs
from grafana_exporter import export_grafana_and_history
from scoring import calculate_scores
from signal_engine import detect_signals
from utils import now_iso

CONFIG_PATH = Path("config.yaml")


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def collect_source(name: str, config: dict) -> list[dict]:
    if name in {"boamp", "bodacc"}:
        return collect_ods(name, config)
    if name == "ted":
        return collect_ted(config)
    if name == "arbeitnow":
        return collect_jobs(config)
    if name == "gdelt":
        return collect_news(config)
    raise ValueError(f"Unknown source: {name}")


def run() -> None:
    config = load_config()
    init_db()
    all_events: list[dict] = []
    source_names = ("boamp", "bodacc", "ted", "arbeitnow", "gdelt")

    for source in source_names:
        if not config.get("sources", {}).get(source, {}).get("enabled", True):
            continue
        started = now_iso()
        seen = saved = 0
        try:
            events = collect_source(source, config)
            seen = len(events)
            all_events.extend(events)
            update_run(source, started, "COLLECTED", seen, 0, None)
            print(f"[{source}] collected={seen}")
        except Exception as exc:
            update_run(source, started, "ERROR", seen, saved, str(exc)[:1000])
            print(f"[{source}] ERROR: {exc}")
            traceback.print_exc()

    try:
        companies = enrich_events(all_events, config, max_lookups=150)
        for company in companies.values():
            upsert_company(company)
        print(f"[companies] enriched={len(companies)}")
    except Exception as exc:
        print(f"[companies] enrichment warning: {exc}")

    saved_by_source: dict[str, int] = {}
    for event in all_events:
        is_new = insert_event(event)
        if is_new:
            saved_by_source[event["source"].lower()] = saved_by_source.get(event["source"].lower(), 0) + 1
        signals = detect_signals(event, config)
        replace_signals_for_event(event["id"], signals)

    for source in source_names:
        if config.get("sources", {}).get(source, {}).get("enabled", True):
            try:
                update_run(source, now_iso(), "OK", 0, saved_by_source.get(source, 0), None)
            except Exception:
                pass

    scores = calculate_scores(config)
    print(f"[scoring] entities={len(scores)}")

    export_outputs(config)
    export_grafana_and_history(config)
    print("[export] output/server_infra_radar.xlsx")
    print("[export] output/alerts.csv")
    print("[export] output/grafana/*.json")
    print("[history] output/history/<timestamp>/")


if __name__ == "__main__":
    run()
