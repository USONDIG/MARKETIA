from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contact_search_providers import search_public_web

ROLE_TERMS = [
    "Infrastructure & Cloud Director",
    "Infrastructure Director",
    "IT Infrastructure",
    "IT Director",
    "DSI",
    "CIO",
    "IT procurement",
    "IT buyer",
]


def _search_company(company: str) -> pd.DataFrame:
    rows: list[dict] = []
    seen: set[str] = set()
    for role in ROLE_TERMS:
        queries = [
            f'site:linkedin.com/in "{company}" "{role}"',
            f'"{company}" "{role}" LinkedIn',
        ]
        for query in queries:
            try:
                results = search_public_web(query, max_results=6, timeout=6)
            except Exception:
                continue
            for result in results:
                url = str(result.get("url") or "").strip()
                key = url or f"{result.get('title')}|{result.get('snippet')}"
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "role_recherche": role,
                    "titre": result.get("title"),
                    "url": url,
                    "extrait": result.get("snippet"),
                    "source": result.get("provider"),
                })
    return pd.DataFrame(rows)


def render_contact_probe(default_company: str = "XPO Logistics") -> None:
    st.markdown("### Recherche contacts à la demande")
    st.caption("Cette recherche s'exécute directement dans le processus Streamlit. Elle ne lance ni collecteurs, ni scoring, ni workflow GitHub Actions.")
    company = st.text_input("Entreprise", value=default_company, key="contact_probe_company")
    if st.button("Rechercher les contacts maintenant", type="primary", key="contact_probe_run"):
        with st.spinner(f"Recherche publique en cours pour {company}…"):
            result = _search_company(company.strip())
        st.session_state["contact_probe_result"] = result
        st.session_state["contact_probe_last_company"] = company.strip()

    result = st.session_state.get("contact_probe_result")
    if isinstance(result, pd.DataFrame):
        if result.empty:
            st.warning("Aucun résultat public récupéré depuis l'environnement Streamlit pour cette recherche.")
        else:
            linkedin_count = int(result["url"].fillna("").str.contains("linkedin.com/in/", case=False, regex=False).sum())
            a, b = st.columns(2)
            a.metric("Résultats", len(result))
            b.metric("Profils LinkedIn", linkedin_count)
            st.dataframe(result, use_container_width=True, hide_index=True, height=min(500, 80 + 38 * len(result)))
