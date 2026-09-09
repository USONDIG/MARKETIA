from __future__ import annotations

from typing import Any

import pandas as pd

from database import connect
from utils import now_iso

ROLE_LIBRARY = {
    "buyer": ["Directeur achats IT", "IT Procurement Manager", "Category Manager IT", "Strategic Buyer IT"],
    "decision_maker": ["DSI / CIO", "CTO", "Head of Infrastructure", "IT Director"],
    "technical_influencer": ["Infrastructure Manager", "IT Operations Manager", "Platform Engineering Manager"],
    "server": ["Head of Infrastructure", "Systems Manager", "Datacenter Manager"],
    "gpu": ["Head of AI Infrastructure", "HPC Manager", "MLOps Lead", "ML Platform Lead"],
    "storage": ["Storage Manager", "Backup Manager", "Infrastructure Manager"],
    "virtualization": ["Cloud Infrastructure Manager", "Virtualization Manager", "Platform Engineering Manager"],
    "network": ["Network Manager", "Head of Network", "Datacenter Network Architect"],
    "datacenter": ["Datacenter Manager", "Head of Infrastructure", "IT Operations Manager"],
    "cloud_repatriation": ["Head of Cloud", "FinOps Lead", "Cloud Infrastructure Manager"],
}

MARKET_ROLE_MAP = {
    "Serveurs / Compute": "server",
    "GPU / HPC / IA": "gpu",
    "Stockage / Backup": "storage",
    "Virtualisation / Private Cloud": "virtualization",
    "Reseau Datacenter": "network",
    "Datacenter / Salle IT": "datacenter",
    "FinOps / Cloud Repatriation": "cloud_repatriation",
}


def build_contact_targets(limit: int = 500) -> pd.DataFrame:
    with connect() as db:
        rows = db.execute(
            """
            SELECT s.entity_key, s.siren, s.company_name, s.opportunity_score,
                   s.priority, s.top_signal
            FROM scores s
            ORDER BY s.opportunity_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        signal_rows = db.execute(
            """
            SELECT COALESCE(e.siren, 'NAME::' || LOWER(COALESCE(e.company_name, ''))) AS entity_key,
                   s.label
            FROM signals s
            JOIN events e ON e.id = s.event_id
            WHERE s.signal_type='market'
            """
        ).fetchall()

    markets_by_entity: dict[str, set[str]] = {}
    for row in signal_rows:
        markets_by_entity.setdefault(str(row["entity_key"]), set()).add(str(row["label"] or ""))

    out: list[dict[str, Any]] = []
    for row in rows:
        entity_key = str(row["entity_key"])
        markets = markets_by_entity.get(entity_key, set())
        roles: list[tuple[str, str, int]] = []
        for title in ROLE_LIBRARY["buyer"]:
            roles.append(("BUYER", title, 85))
        for title in ROLE_LIBRARY["decision_maker"]:
            roles.append(("DECISION_MAKER", title, 90))
        for market in markets:
            key = MARKET_ROLE_MAP.get(market)
            if key:
                for title in ROLE_LIBRARY[key]:
                    roles.append(("TECHNICAL_INFLUENCER", title, 95))

        seen: set[tuple[str, str]] = set()
        for role_class, title, relevance in roles:
            if (role_class, title) in seen:
                continue
            seen.add((role_class, title))
            out.append({
                "entity_key": entity_key,
                "siren": row["siren"],
                "company_name": row["company_name"],
                "opportunity_score": row["opportunity_score"],
                "priority": row["priority"],
                "role_class": role_class,
                "target_title": title,
                "relevance_score": relevance,
                "markets": ", ".join(sorted(markets)),
                "preferred_sources": "LinkedIn, réseaux professionnels, site corporate, conférences/speakers",
                "generated_at": now_iso(),
            })
    return pd.DataFrame(out)


def load_contacts() -> pd.DataFrame:
    with connect() as db:
        return pd.read_sql_query(
            """
            SELECT entity_key, siren, company_name, full_name, job_title, role_class,
                   relevance_score, linkedin_url, professional_email, professional_phone,
                   source_name, source_url, confidence, verified_at, status, updated_at
            FROM contacts
            ORDER BY relevance_score DESC, updated_at DESC
            """,
            db,
        )
