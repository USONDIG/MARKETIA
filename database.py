from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path("data/radar.db")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                siren TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                naf TEXT,
                city TEXT,
                employees TEXT,
                sites INTEGER,
                website TEXT,
                headquarters_country TEXT DEFAULT 'FR',
                raw_json TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS company_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                siren TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                naf TEXT,
                employees TEXT,
                sites INTEGER,
                city TEXT,
                UNIQUE(siren, snapshot_at)
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_siren ON company_snapshots(siren);

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                siren TEXT,
                company_name TEXT,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_date TEXT,
                title TEXT,
                content TEXT,
                url TEXT,
                country TEXT,
                raw_json TEXT,
                collected_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_siren ON events(siren);
            CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
            CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                siren TEXT,
                signal_type TEXT NOT NULL,
                label TEXT,
                strength REAL NOT NULL,
                weight REAL NOT NULL,
                matched_terms TEXT,
                detected_at TEXT NOT NULL,
                UNIQUE(event_id, signal_type, label)
            );
            CREATE INDEX IF NOT EXISTS idx_signals_siren ON signals(siren);

            CREATE TABLE IF NOT EXISTS scores (
                entity_key TEXT PRIMARY KEY,
                siren TEXT,
                company_name TEXT,
                infra_fit REAL NOT NULL,
                buying_intent REAL NOT NULL,
                timing REAL NOT NULL,
                opportunity_score REAL NOT NULL,
                priority TEXT NOT NULL,
                top_signal TEXT,
                calculated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                source TEXT PRIMARY KEY,
                last_run TEXT,
                last_status TEXT,
                records_seen INTEGER DEFAULT 0,
                records_saved INTEGER DEFAULT 0,
                error TEXT
            );
            """
        )


def upsert_company(company: dict[str, Any]) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT INTO companies (
                siren, name, naf, city, employees, sites, website,
                headquarters_country, raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(siren) DO UPDATE SET
                name=excluded.name,
                naf=COALESCE(excluded.naf, companies.naf),
                city=COALESCE(excluded.city, companies.city),
                employees=COALESCE(excluded.employees, companies.employees),
                sites=COALESCE(excluded.sites, companies.sites),
                website=COALESCE(excluded.website, companies.website),
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            (
                company["siren"], company.get("name") or company["siren"],
                company.get("naf"), company.get("city"), company.get("employees"),
                company.get("sites"), company.get("website"),
                company.get("headquarters_country", "FR"),
                json.dumps(company.get("raw", company), ensure_ascii=False),
                company["updated_at"],
            ),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO company_snapshots
                (siren, snapshot_at, naf, employees, sites, city)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                company["siren"], company["updated_at"], company.get("naf"),
                company.get("employees"), company.get("sites"), company.get("city")
            ),
        )


def get_previous_snapshot(siren: str) -> sqlite3.Row | None:
    with connect() as db:
        return db.execute(
            """
            SELECT * FROM company_snapshots
            WHERE siren=?
            ORDER BY snapshot_at DESC
            LIMIT 1 OFFSET 1
            """,
            (siren,),
        ).fetchone()


def insert_event(event: dict[str, Any]) -> bool:
    with connect() as db:
        cur = db.execute(
            """
            INSERT OR IGNORE INTO events (
                id, siren, company_name, source, event_type, event_date,
                title, content, url, country, raw_json, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"], event.get("siren"), event.get("company_name"),
                event["source"], event.get("event_type", "event"), event.get("event_date"),
                event.get("title"), event.get("content"), event.get("url"),
                event.get("country"), json.dumps(event.get("raw", event), ensure_ascii=False),
                event["collected_at"],
            ),
        )
        return cur.rowcount > 0


def replace_signals_for_event(event_id: str, signals: Iterable[dict[str, Any]]) -> None:
    with connect() as db:
        db.execute("DELETE FROM signals WHERE event_id=?", (event_id,))
        for signal in signals:
            db.execute(
                """
                INSERT OR IGNORE INTO signals (
                    event_id, siren, signal_type, label, strength, weight,
                    matched_terms, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, signal.get("siren"), signal["signal_type"], signal.get("label"),
                    signal.get("strength", 1), signal.get("weight", 0),
                    json.dumps(signal.get("matched_terms", []), ensure_ascii=False),
                    signal["detected_at"],
                ),
            )


def save_score(score: dict[str, Any]) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT INTO scores (
                entity_key, siren, company_name, infra_fit, buying_intent,
                timing, opportunity_score, priority, top_signal, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_key) DO UPDATE SET
                siren=excluded.siren,
                company_name=excluded.company_name,
                infra_fit=excluded.infra_fit,
                buying_intent=excluded.buying_intent,
                timing=excluded.timing,
                opportunity_score=excluded.opportunity_score,
                priority=excluded.priority,
                top_signal=excluded.top_signal,
                calculated_at=excluded.calculated_at
            """,
            (
                score["entity_key"], score.get("siren"), score.get("company_name"),
                score["infra_fit"], score["buying_intent"], score["timing"],
                score["opportunity_score"], score["priority"], score.get("top_signal"),
                score["calculated_at"],
            ),
        )


def update_run(source: str, when: str, status: str, seen: int, saved: int, error: str | None = None) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT INTO runs(source, last_run, last_status, records_seen, records_saved, error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_run=excluded.last_run,
                last_status=excluded.last_status,
                records_seen=excluded.records_seen,
                records_saved=excluded.records_saved,
                error=excluded.error
            """,
            (source, when, status, seen, saved, error),
        )
