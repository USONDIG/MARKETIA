from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

REPO = "USONDIG/MARKETIA"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/output/grafana"

st.set_page_config(page_title="MARKETIA Besoins probables", page_icon="💡", layout="wide")

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


def render_table(df: pd.DataFrame, prefix: str, score_column: str) -> None:
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    themes = sorted(df.get("business_theme", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    countries = sorted(df.get("country", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())

    with st.expander("Filtres", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            selected_themes = st.multiselect("Thème probable", themes, default=themes, key=f"{prefix}_themes")
        with c2:
            selected_countries = st.multiselect("Pays", countries, default=countries, key=f"{prefix}_countries")
        with c3:
            min_confidence = st.slider("Confiance minimum", 0, 100, 0, key=f"{prefix}_confidence")
        with c4:
            min_score = st.slider("Score minimum", 0, 100, 0, key=f"{prefix}_score")
        search = st.text_input("Entreprise / thème / justification contient", "", key=f"{prefix}_search")

    filtered = df.copy()
    if selected_themes and "business_theme" in filtered.columns:
        filtered = filtered[filtered["business_theme"].isin(selected_themes)]
    if selected_countries and "country" in filtered.columns:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if "theme_confidence" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["theme_confidence"], errors="coerce").fillna(0) >= min_confidence]
    if score_column in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered[score_column], errors="coerce").fillna(0) >= min_score]
    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ["company_name", "business_theme", "business_theme_secondary", "theme_reason", "recommended_angle", "likely_contact_roles"]:
            if column in filtered.columns:
                mask |= filtered[column].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    st.caption(f"{len(filtered)} lignes après filtrage")
    preferred = [
        "priority", "discovery_priority", score_column, "company_name", "country",
        "employee_range", "business_theme", "business_theme_secondary", "theme_confidence",
        "theme_reason", "recommended_angle", "likely_contact_roles", "top_signal", "top_signals",
        "markets", "latest_event_date", "latest_url",
    ]
    columns = []
    for column in preferred:
        if column in filtered.columns and column not in columns:
            columns.append(column)
    st.dataframe(filtered[columns] if columns else filtered, use_container_width=True, hide_index=True, height=650)


st.title("💡 Besoins probables / angles commerciaux")
st.caption(
    "Interprétation des signaux croisés MARKETIA : besoin client probable, niveau de confiance, "
    "justification, angle commercial recommandé et fonctions à approcher."
)

try:
    opportunities = safe_df(load_feed("opportunities.json"))
    discovery = safe_df(load_feed("discovery.json"))
except Exception as exc:
    st.error(f"Impossible de charger les données : {exc}")
    st.stop()

if st.button("Actualiser les données"):
    load_feed.clear()
    st.rerun()

qualified_tab, discovery_tab = st.tabs(["🎯 Opportunités qualifiées", "📡 Radar / Discovery"])
with qualified_tab:
    render_table(opportunities, "qualified", "opportunity_score")
with discovery_tab:
    render_table(discovery, "discovery", "discovery_score")
