from __future__ import annotations

import pandas as pd
import streamlit as st

from shared_ui import clean_values, render_lead_detail, render_shared_filters, safe_df


def render_radar_discovery(load_feed, *, key_prefix: str = "radar") -> None:
    st.subheader("Radar / Discovery")
    st.caption("Vue précoce des leads détectés, y compris ceux qui ne sont pas encore totalement qualifiés.")

    try:
        discovery = safe_df(load_feed("discovery.json"))
        stats = safe_df(load_feed("dashboard_stats.json"))
        contacts = safe_df(load_feed("contacts.json"))
        contact_targets = safe_df(load_feed("contact_targets.json"))
    except Exception as exc:
        st.error(f"Impossible de charger le Radar Discovery : {exc}")
        return

    if not stats.empty:
        row = stats.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Détectés", int(row.get("discovery_entities", 0) or 0))
        c2.metric("HIGH", int(row.get("discovery_high", 0) or 0))
        c3.metric("MEDIUM", int(row.get("discovery_medium", 0) or 0))
        c4.metric("Identifiés +", int(row.get("identified_or_better", 0) or 0))
        c5.metric("Qualifiés", int(row.get("qualified_from_discovery", 0) or 0))

    if discovery.empty:
        st.info("Aucun compte Discovery disponible.")
        return

    filtered = render_shared_filters(discovery)
    a, b, c = st.columns([2, 2, 1])
    with a:
        priorities = clean_values(filtered, "discovery_priority")
        selected_priorities = st.multiselect("Priorité Discovery", priorities, key=f"{key_prefix}_priority", placeholder="Toutes") if priorities else []
    with b:
        statuses = clean_values(filtered, "status")
        selected_statuses = st.multiselect("Statut", statuses, key=f"{key_prefix}_status", placeholder="Tous") if statuses else []
    with c:
        min_score = st.slider("Score Discovery minimum", 0, 100, 0, key=f"{key_prefix}_score")

    if selected_priorities and "discovery_priority" in filtered.columns:
        filtered = filtered[filtered["discovery_priority"].astype(str).isin(selected_priorities)]
    if selected_statuses and "status" in filtered.columns:
        filtered = filtered[filtered["status"].astype(str).isin(selected_statuses)]
    if "discovery_score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["discovery_score"], errors="coerce").fillna(0) >= min_score]

    st.markdown(f"## Leads détectés — {len(filtered)}")
    cols = [c for c in [
        "discovery_priority", "discovery_score", "status", "company_name", "country", "employee_range",
        "business_theme", "theme_confidence", "markets", "top_signals", "latest_event_date",
    ] if c in filtered.columns]
    st.dataframe(filtered[cols] if cols else filtered, use_container_width=True, hide_index=True, height=430)

    if filtered.empty or "company_name" not in filtered.columns:
        return

    rows = filtered.reset_index(drop=True)
    labels = [f"{row.get('company_name', 'Lead')} — {row.get('business_theme', 'Besoin à préciser')} — score {row.get('discovery_score', '—')}" for _, row in rows.iterrows()]
    selected = st.selectbox("Lead sélectionné", labels, key=f"{key_prefix}_selected_lead")
    lead = rows.iloc[labels.index(selected)]
    render_lead_detail(lead, contacts, contact_targets, score_field="discovery_score", score_label="Score Discovery")

    st.info("Le Radar est volontairement plus large que le Dashboard : un lead peut être intéressant mais rester non qualifié tant que les informations entreprise nécessaires ne sont pas disponibles.")
