from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

REPO = "USONDIG/MARKETIA"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/output/grafana"

st.set_page_config(page_title="MARKETIA Contacts", page_icon="👥", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Connecte-toi d'abord depuis la page principale MARKETIA.")
    st.stop()


@st.cache_data(ttl=60, show_spinner=False)
def load_feed(name: str):
    response = requests.get(f"{RAW_BASE}/{name}", timeout=20)
    response.raise_for_status()
    return response.json()


def safe_df(payload) -> pd.DataFrame:
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        return pd.DataFrame([payload])
    return pd.DataFrame()


st.title("👥 Contacts clés")
st.caption("Rôles à cibler et personnes identifiées pour les opportunités MARKETIA.")

try:
    targets = safe_df(load_feed("contact_targets.json"))
    contacts = safe_df(load_feed("contacts.json"))
except Exception as exc:
    st.error(f"Impossible de charger la couche Contacts : {exc}")
    st.stop()

if st.button("Actualiser les contacts"):
    load_feed.clear()
    st.rerun()

c1, c2, c3 = st.columns(3)
c1.metric("Rôles cibles", len(targets))
c2.metric("Contacts identifiés", len(contacts))
c3.metric("Emails pro vérifiés", int(contacts.get("professional_email", pd.Series(dtype=str)).notna().sum()) if not contacts.empty else 0)

st.markdown("### Rôles recommandés par opportunité")
if targets.empty:
    st.info("Aucun rôle cible généré pour l'instant.")
else:
    companies = sorted(targets["company_name"].dropna().astype(str).unique().tolist())
    role_classes = sorted(targets["role_class"].dropna().astype(str).unique().tolist())
    a, b, c = st.columns(3)
    with a:
        selected_companies = st.multiselect("Entreprise", companies, default=[])
    with b:
        selected_roles = st.multiselect("Type de rôle", role_classes, default=role_classes)
    with c:
        min_relevance = st.slider("Pertinence minimum", 0, 100, 80)

    filtered = targets.copy()
    if selected_companies:
        filtered = filtered[filtered["company_name"].isin(selected_companies)]
    if selected_roles:
        filtered = filtered[filtered["role_class"].isin(selected_roles)]
    filtered = filtered[pd.to_numeric(filtered["relevance_score"], errors="coerce").fillna(0) >= min_relevance]
    cols = [c for c in ["company_name", "priority", "opportunity_score", "role_class", "target_title", "relevance_score", "markets", "preferred_sources"] if c in filtered.columns]
    st.dataframe(filtered[cols], use_container_width=True, hide_index=True, height=420)

st.markdown("### Personnes identifiées")
if contacts.empty:
    st.info("Aucun contact nominatif n'est encore enregistré. La prochaine étape sera de brancher les sources autorisées de découverte/enrichissement.")
else:
    cols = [c for c in ["company_name", "full_name", "job_title", "role_class", "relevance_score", "linkedin_url", "professional_email", "professional_phone", "source_name", "source_url", "confidence", "verified_at", "status"] if c in contacts.columns]
    st.dataframe(contacts[cols], use_container_width=True, hide_index=True, height=520)

st.caption("Sources privilégiées prévues : LinkedIn et réseaux professionnels pour identifier les fonctions/personnes, complétés par sites corporate, conférences/speakers et sources publiques. Aucun scraping LinkedIn non autorisé n'est activé par cette couche.")
