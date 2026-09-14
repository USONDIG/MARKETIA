from __future__ import annotations

import pandas as pd
import streamlit as st

from shared_filters import render_filters
from shared_ui import clean_values, has_value, render_lead_detail, safe_df


def _key(row: pd.Series) -> str:
    siren = str(row.get("siren") or "").strip()
    return f"SIREN::{siren}" if siren and siren.casefold() not in {"nan", "none"} else f"NAME::{str(row.get('company_name') or '').strip().casefold()}"


def _contacts_view(contacts: pd.DataFrame, opportunities: pd.DataFrame, discovery: pd.DataFrame) -> pd.DataFrame:
    if contacts.empty:
        return pd.DataFrame()
    meta = {}
    for _, row in discovery.iterrows():
        meta[_key(row)] = {"score": row.get("discovery_score"), "priority": row.get("discovery_priority"), "business_theme": row.get("business_theme")}
    for _, row in opportunities.iterrows():
        meta[_key(row)] = {"score": row.get("opportunity_score"), "priority": row.get("priority"), "business_theme": row.get("business_theme")}
    rows = []
    for _, contact in contacts.iterrows():
        extra = meta.get(_key(contact), {})
        rows.append({
            "priority": extra.get("priority"), "score": extra.get("score"), "company_name": contact.get("company_name"),
            "business_theme": extra.get("business_theme"), "full_name": contact.get("full_name"), "job_title": contact.get("job_title"),
            "role_class": contact.get("role_class"), "linkedin_url": contact.get("linkedin_url"), "professional_email": contact.get("professional_email"),
            "professional_phone": contact.get("professional_phone"), "confidence": contact.get("confidence"), "source_url": contact.get("source_url"),
        })
    return pd.DataFrame(rows)


def _render_contacts(contacts: pd.DataFrame, opportunities: pd.DataFrame, discovery: pd.DataFrame) -> None:
    st.markdown("## Contacts disponibles maintenant")
    actionable = _contacts_view(contacts, opportunities, discovery)
    if actionable.empty:
        st.info("Aucun contact nominatif validé pour le moment. Les prochains runs continueront la recherche.")
        return
    linkedin = has_value(actionable["linkedin_url"]); email = has_value(actionable["professional_email"]); phone = has_value(actionable["professional_phone"])
    a, b, c, d = st.columns(4)
    a.metric("Contacts", len(actionable)); b.metric("LinkedIn", int(linkedin.sum())); c.metric("Email pro", int(email.sum())); d.metric("Téléphone", int(phone.sum()))
    roles = clean_values(actionable, "role_class")
    f1, f2, f3 = st.columns([2, 2, 3])
    availability = [label for label, ok in [("LinkedIn", linkedin.any()), ("Email pro", email.any()), ("Téléphone", phone.any())] if ok]
    with f1: selected_availability = st.multiselect("Coordonnée disponible", availability, key="contacts_availability_v2") if availability else []
    with f2: selected_roles = st.multiselect("Type de contact", roles, key="contacts_roles_v2") if roles else []
    with f3: search = st.text_input("Entreprise / contact / fonction", key="contacts_search_v2")
    filtered = actionable.copy()
    if selected_roles: filtered = filtered[filtered["role_class"].astype(str).isin(selected_roles)]
    if selected_availability:
        mask = pd.Series(True, index=filtered.index)
        if "LinkedIn" in selected_availability: mask &= has_value(filtered["linkedin_url"])
        if "Email pro" in selected_availability: mask &= has_value(filtered["professional_email"])
        if "Téléphone" in selected_availability: mask &= has_value(filtered["professional_phone"])
        filtered = filtered[mask]
    if search:
        mask = pd.Series(False, index=filtered.index)
        for col in ["company_name", "full_name", "job_title", "business_theme"]: mask |= filtered[col].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]
    st.dataframe(filtered, use_container_width=True, hide_index=True, height=320)


def render_dashboard(load_feed, render_run_status) -> None:
    st.subheader("Dashboard")
    st.caption("Que dois-je traiter maintenant ? Opportunités qualifiées, contacts disponibles et contexte commercial.")
    render_run_status(compact=True)
    try:
        stats = safe_df(load_feed("dashboard_stats.json")); opportunities = safe_df(load_feed("opportunities.json")); discovery = safe_df(load_feed("discovery.json"))
        signals = safe_df(load_feed("signals.json")); events = safe_df(load_feed("events.json")); contacts = safe_df(load_feed("contacts.json")); targets = safe_df(load_feed("contact_targets.json"))
    except Exception as exc:
        st.error(f"Impossible de charger les flux MARKETIA : {exc}"); return
    row = stats.iloc[0] if not stats.empty else pd.Series(dtype=object); actionable = _contacts_view(contacts, opportunities, discovery)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Opportunités", int(row.get("opportunities", len(opportunities)) or 0)); m2.metric("À contacter", len(actionable)); m3.metric("HOT / WARM", int(row.get("hot", 0) or 0) + int(row.get("warm", 0) or 0)); m4.metric("Leads Radar", int(row.get("discovery_medium", 0) or 0) + int(row.get("discovery_high", 0) or 0)); m5.metric("Score moyen", f"{float(row.get('avg_score', 0) or 0):.1f}")
    if opportunities.empty:
        st.info("Aucune opportunité qualifiée pour le moment. Consulte Radar / Discovery pour les leads émergents."); _render_contacts(contacts, opportunities, discovery); return
    filtered = render_filters(opportunities, "dashboard")
    a, b = st.columns([2, 1])
    with a:
        priorities = clean_values(filtered, "priority"); selected = st.multiselect("Priorité commerciale", priorities, key="dashboard_priority_v2", placeholder="Toutes") if priorities else []
    with b: minimum = st.slider("Score opportunité minimum", 0, 100, 0, key="dashboard_score_v2")
    if selected and "priority" in filtered.columns: filtered = filtered[filtered["priority"].astype(str).isin(selected)]
    if "opportunity_score" in filtered.columns: filtered = filtered[pd.to_numeric(filtered["opportunity_score"], errors="coerce").fillna(0) >= minimum]
    st.markdown(f"## Opportunités à traiter — {len(filtered)}")
    cols = [c for c in ["priority", "opportunity_score", "company_name", "country", "employee_range", "business_theme", "theme_confidence", "top_signal"] if c in filtered.columns]
    st.dataframe(filtered[cols] if cols else filtered, use_container_width=True, hide_index=True, height=360)
    if not filtered.empty and "company_name" in filtered.columns:
        rows = filtered.reset_index(drop=True); labels = [f"{r.get('company_name', 'Lead')} — {r.get('business_theme', 'Besoin à préciser')} — score {r.get('opportunity_score', '—')}" for _, r in rows.iterrows()]
        choice = st.selectbox("Opportunité sélectionnée", labels, key="dashboard_lead_v2"); lead = rows.iloc[labels.index(choice)]
        render_lead_detail(lead, contacts, targets, score_field="opportunity_score", score_label="Score opportunité", signals=signals, events=events)
    st.divider(); _render_contacts(contacts, opportunities, discovery)
