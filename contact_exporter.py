from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from contacts import build_contact_targets, load_contacts

GRAFANA_DIR = Path("output/grafana")


def _records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    clean = df.where(pd.notnull(df), None)
    return clean.to_dict(orient="records")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def export_contact_feeds(config: dict) -> None:
    settings = config.get("contacts", {})
    if not settings.get("enabled", True):
        return

    target_limit = int(settings.get("target_limit", 500))
    targets = build_contact_targets(limit=target_limit)
    contacts = load_contacts()

    _write_json(GRAFANA_DIR / "contact_targets.json", _records(targets))
    _write_json(GRAFANA_DIR / "contacts.json", _records(contacts))
