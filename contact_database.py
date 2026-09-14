from __future__ import annotations

from typing import Any

from database import connect
from utils import now_iso


EVIDENCE_COLUMNS = {
    "role_evidence": "TEXT",
    "linkedin_status": "TEXT",
    "email_status": "TEXT",
    "phone_status": "TEXT",
    "evidence_summary": "TEXT",
}


def _ensure_contact_columns(db) -> None:
    existing = {str(row["name"]) for row in db.execute("PRAGMA table_info(contacts)").fetchall()}
    for column, sql_type in EVIDENCE_COLUMNS.items():
        if column not in existing:
            db.execute(f"ALTER TABLE contacts ADD COLUMN {column} {sql_type}")


def init_contact_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                siren TEXT,
                company_name TEXT NOT NULL,
                full_name TEXT NOT NULL,
                job_title TEXT,
                role_class TEXT,
                relevance_score REAL DEFAULT 0,
                linkedin_url TEXT,
                professional_email TEXT,
                professional_phone TEXT,
                source_name TEXT,
                source_url TEXT,
                confidence REAL DEFAULT 0,
                verified_at TEXT,
                status TEXT DEFAULT 'DISCOVERED',
                role_evidence TEXT,
                linkedin_status TEXT,
                email_status TEXT,
                phone_status TEXT,
                evidence_summary TEXT,
                raw_json TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(entity_key, full_name, job_title)
            );
            CREATE INDEX IF NOT EXISTS idx_contacts_entity ON contacts(entity_key);
            CREATE INDEX IF NOT EXISTS idx_contacts_siren ON contacts(siren);
            CREATE INDEX IF NOT EXISTS idx_contacts_role ON contacts(role_class);
            CREATE INDEX IF NOT EXISTS idx_contacts_relevance ON contacts(relevance_score);
            """
        )
        _ensure_contact_columns(db)


def upsert_contact(contact: dict[str, Any]) -> None:
    with connect() as db:
        _ensure_contact_columns(db)
        db.execute(
            """
            INSERT INTO contacts (
                entity_key, siren, company_name, full_name, job_title, role_class,
                relevance_score, linkedin_url, professional_email, professional_phone,
                source_name, source_url, confidence, verified_at, status,
                role_evidence, linkedin_status, email_status, phone_status, evidence_summary,
                raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_key, full_name, job_title) DO UPDATE SET
                role_class=excluded.role_class,
                relevance_score=MAX(contacts.relevance_score, excluded.relevance_score),
                linkedin_url=COALESCE(excluded.linkedin_url, contacts.linkedin_url),
                professional_email=COALESCE(excluded.professional_email, contacts.professional_email),
                professional_phone=COALESCE(excluded.professional_phone, contacts.professional_phone),
                source_name=COALESCE(excluded.source_name, contacts.source_name),
                source_url=COALESCE(excluded.source_url, contacts.source_url),
                confidence=MAX(contacts.confidence, excluded.confidence),
                verified_at=COALESCE(excluded.verified_at, contacts.verified_at),
                status=excluded.status,
                role_evidence=COALESCE(excluded.role_evidence, contacts.role_evidence),
                linkedin_status=COALESCE(excluded.linkedin_status, contacts.linkedin_status),
                email_status=COALESCE(excluded.email_status, contacts.email_status),
                phone_status=COALESCE(excluded.phone_status, contacts.phone_status),
                evidence_summary=COALESCE(excluded.evidence_summary, contacts.evidence_summary),
                raw_json=COALESCE(excluded.raw_json, contacts.raw_json),
                updated_at=excluded.updated_at
            """,
            (
                contact["entity_key"], contact.get("siren"), contact["company_name"],
                contact["full_name"], contact.get("job_title"), contact.get("role_class"),
                float(contact.get("relevance_score", 0)), contact.get("linkedin_url"),
                contact.get("professional_email"), contact.get("professional_phone"),
                contact.get("source_name"), contact.get("source_url"),
                float(contact.get("confidence", 0)), contact.get("verified_at"),
                contact.get("status", "DISCOVERED"), contact.get("role_evidence"),
                contact.get("linkedin_status"), contact.get("email_status"),
                contact.get("phone_status"), contact.get("evidence_summary"),
                contact.get("raw_json"), contact.get("updated_at") or now_iso(),
            ),
        )
