from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

REPO = "USONDIG/MARKETIA"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/output/grafana"

st.set_page_config(page_title="MARKETIA Radar Discovery", page_icon="📡", layout="wide")

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


st.title("📡 Radar / Discovery")
st.caption(
    "Vue large des comptes détectés par MARKETIA. Cette liste conserve les signaux intéressants "
    "même lorsque l'entreprise n'est pas encore totalement enrichie ou qualifiée."
)

try:
    discovery = safe_df(load_feed("discovery.json"))
    stats = safe_df(load_feed("dashboard_stats.json"))
except Exception as exc:
    st.error(f"Impossible de charger le Radar Discovery : {exc}")
    st.stop()

if st.button("Actualiser les données"):
    load_feed.clear()
    st.rerun()

if not stats.empty:
    row = stats.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Détectées", int(row.get("discovery_entities", 0) or 0))
    c2.metric("HIGH", int(row.get("discovery_high", 0) or 0))
    c3.metric("MEDIUM", int(row.get("discovery_medium", 0) or 0))
    c4.metric("Identifiées +", int(row.get("identified_or_better", 0) or 0))
    c5.metric("Qualifiées", int(row.get("qualified_from_discovery", 0) or 0))

if discovery.empty:
    st.info("Aucun compte Discovery n'est encore disponible. Lance un run MARKETIA.")
    st.stop()

with st.expander("Filtres", expanded=True):
    a, b, c, d = st.columns(4)
    priorities = sorted(discovery.get("discovery_priority", pd.Series(dtype=str)).dropna().astype(str).unique())
    statuses = sorted(discovery.get("status", pd.Series(dtype=str)).dropna().astype(str).unique())
    countries = sorted(discovery.get("country", pd.Series(dtype=str)).dropna().astype(str).unique())
    with a:
        selected_priorities = st.multiselect("Priorité Discovery", priorities, default=priorities)
    with b:
        selected_statuses = st.multiselect("Statut", statuses, default=statuses)
    with c:
        selected_countries = st.multiselect("Pays", countries, default=countries)
    with d:
        min_score = st.slider("Score Discovery minimum", 0, 100, 0)
    search = st.text_input("Entreprise / signal / marché contient", "")

filtered = discovery.copy()
if selected_priorities and "discovery_priority" in filtered.columns:
    filtered = filtered[filtered["discovery_priority"].isin(selected_priorities)]
if selected_statuses and "status" in filtered.columns:
    filtered = filtered[filtered["status"].isin(selected_statuses)]
if selected_countries and "country" in filtered.columns:
    filtered = filtered[filtered["country"].isin(selected_countries)]
if "discovery_score" in filtered.columns:
    filtered = filtered[pd.to_numeric(filtered["discovery_score"], errors="coerce").fillna(0) >= min_score]
if search:
    searchable = pd.Series(False, index=filtered.index)
    for column in ["company_name", "markets", "top_signals", "sources"]:
        if column in filtered.columns:
            searchable |= filtered[column].astype(str).str.contains(search, case=False, na=False)
    filtered = filtered[searchable]

st.markdown(f"### Comptes détectés — {len(filtered)}")
preferred = [
    "discovery_priority", "discovery_score", "status", "company_name", "country",
    "naf", "employee_range", "event_count", "signal_count", "sources", "markets",
    "top_signals", "latest_event_date", "latest_title", "latest_url",
]
columns = [column for column in preferred if column in filtered.columns]
st.dataframe(filtered[columns] if columns else filtered, use_container_width=True, hide_index=True, height=650)

st.info(
    "Lecture des statuts : DISCOVERED = signal détecté mais identité/métadonnées incomplètes ; "
    "IDENTIFIED = entreprise identifiée ; ENRICHED = métadonnées disponibles mais cible non validée ; "
    "QUALIFIED = conforme au ciblage MARKETIA (dont le seuil d'effectif configuré)."
)
