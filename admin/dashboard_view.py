from __future__ import annotations

import pandas as pd
import streamlit as st

from shared_ui import clean_values, has_value, render_lead_detail, render_shared_filters, safe_df


def _lead_key(row: pd.Series) -> str:
    siren = str(row.get("siren") or "").strip()
    if siren and siren.casefold() not in {"nan", "none"}:
        return f"SIREN::{siren}"
    return f"NAME::{str(row.get('company_name') or '').strip().casefold()}"


def _build_actionable_contacts(contacts: pd.DataFrame, opportunities: pd.DataFrame, discovery: pd.DataFrame) -> pd.DataFrame:
    if contacts.empty:
        return pd.DataFrame()
    metadata: dict[str, dict] = {}
    for _, row in discovery.iterrows():
        metadata[_lead_key(row)] = {
            "lead_status": str(row.get("status") or "DISCOVERY"),
            "score": row.get("discovery_score"),
            "priority": row.get("discovery_priority"),
            "business_theme": row.get("business_theme"),
            "country": row.get("country"),
            "recommended_angle": row.get("recommended_angle"),
        }
    for _, row in opportunities.iterrows():
        metadata[_lead_key(row)] = {
            "lead_status": "QUALIFIED",
            "score": row.get("opportunity_score"),
            "priority": row.get("priority"),
            "business_theme": row.get("business_theme"),
            "country": row.get("country"),
            "recommended_angle": row.get("recommended_angle"),
        }
    rows = []
    for _, contact in contacts.iterrows():
        meta = metadata.get(_lead_key(contact), {})
        rows.append({
            "lead_status": meta.get("lead_status", "CONTACT_ONLY"),
            "priority": meta.get("priority"),
            "score": meta.get("score"),
            "company_name": contact.get("company_name"),
            "country": meta.get("country"),
            "business_theme": meta.get("business_theme"),
            "full_name": contact.get("full_name"),
            "job_title": contact.get("job_title"),
            "role_class": contact.get("role_class"),
            "linkedin_url": contact.get("linkedin_url"),
            "professional_email": contact.get("professional_email"),
            "professional_phone": contact.get("professional_phone"),
            "confidence": contact.get("confidence"),
            "source_url": contact.get("source_url"),
            "recommended_angle": meta.get("recommended_angle"),
        })
    return pd.DataFrame(rows)


def _render_contacts(contacts: pd.DataFrame, opportunities: pd.DataFrame, discovery: pd.DataFrame) -> None:
    st.markdown("## 👥 Contacts disponibles maintenant")
    st.caption("Cette liste ne contient que les leads pour lesquels MARKETIA a identifié une personne exploitable.")
    actionable = _build_actionable_contacts(contacts, opportunities, discovery)
    if actionable.empty:
        st.info("Aucun contact nominatif validé pour le moment. Les prochains runs continueront la recherche.")
        return

    linkedin = has_value(actionable.get("linkedin_url", pd.Series(index=actionable.index, dtype=str)))
    email = has_value(actionable.get("professional_email", pd.Series(index=actionable.index, dtype=str)))
    phone = has_value(actionable.get("professional_phone", pd.Series(index=actionable.index, dtype=str)))
    a, b, c, d = st.columns(4)
    a.metric("Contacts", len(actionable))
    b.metric("LinkedIn", int(linkedin.sum()))
    c.metric("Email pro", int(email.sum()))
    d.metric("Téléphone", int(phone.sum()))

    roles = clean_values(actionable, "role_class")
    availability = []
    if linkedin.any():
        availability.append("LinkedIn")
    if email.any():
        availability.append("Email pro")
    if phone.any():
        availability.append("Téléphone")

    f1, f2, f3 = st.columns([2, 2, 3])
    with f1:
        selected_availability = st.multiselect("Coordonnée disponible", availability, key="dashboard_contact_availability") if availability else []
    with f2:
        selected_roles = st.multiselect("Type de contact", roles, key="dashboard_contact_roles") if roles else []
    with f3:
        search = st.text_input("Entreprise / contact / fonction", key="dashboard_contact_search")

    filtered = actionable.copy()
    if selected_roles:
        filtered = filtered[filtered["role_class"].astype(str).isin(selected_roles)]
    if selected_availability:
        mask = pd.Series(True, index=filtered.index)
        if "LinkedIn" in selected_availability:
            mask &= has_value(filtered["linkedin_url"])
        if "Email pro" in selected_availability:
            mask &= has_value(filtered["professional_email"])
        if "Téléphone" in selected_availability:
            mask &= has_value(filtered["professional_phone"])
        filtered = filtered[mask]
    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ["company_name", "full_name", "job_title", "business_theme"]:
            mask |= filtered[column].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    cols = [c for c in [
        "priority", "score", "company_name", "business_theme", "full_name", "job_title", "role_class",
        "linkedin_url", "professional_email", "professional_phone", "confidence", "source_url",
    ] if c in filtered.columns]
    st.dataframe(filtered[cols], use_container_width=True, hide_index=True, height=320)


def render_qualified_dashboard(load_feed, render_run_status) -> None:
    st.subheader("Dashboard")
    st.caption("Que dois-je traiter maintenant ? Opportunités qualifiées, contacts disponibles et contexte commercial.")
    render_run_status(compact=True)

    try:
        stats = safe_df(load_feed("dashboard_stats.json"))
        opportunities = safe_df(load_feed("opportunities.json"))
        discovery = safe_df(load_feed("discovery.json"))
        signals = safe_df(load_feed("signals.json"))
        events = safe_df(load_feed("events.json"))
        contacts = safe_df(load_feed("contacts.json"))
        contact_targets = safe_df(load_feed("contact_targets.json"))
    except Exception as exc:
        st.error(f"Impossible de charger les flux MARKETIA : {exc}")
        return

    row = stats.iloc[0] if not stats.empty else pd.Series(dtype=object)
    actionable = _build_actionable_contacts(contacts, opportunities, discovery)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Opportunités", int(row.get("opportunities", len(opportunities)) or 0))
    m2.metric("À contacter", len(actionable))
    m3.metric("HOT / WARM", int(row.get("hot", 0) or 0) + int(row.get("warm", 0) or 0))
    m4.metric("Leads Radar", int(row.get("discovery_medium", 0) or 0) + int(row.get("discovery_high", 0) or 0))
    generated_at = str(row.get("generated_at") or "—").replace("T", " ").replace("Z", " UTC")
    m5.metric("Dernière donnée", generated_at[:16] if generated_at != "—" else "—")

    if opportunities.empty:
        st.info("Aucune opportunité qualifiée pour le moment. Consulte Radar / Discovery pour les leads émergents.")
        _render_contacts(contacts, opportunities, discovery)
        return

    filtered = render_shared_filters(opportunities)

    p1, p2 = st.columns([2, 1])
    with p1:
        priorities = clean_values(filtered, "priority")
        selected_priorities = st.multiselect("Priorité commerciale", priorities, key="dashboard_priority", placeholder="Toutes") if priorities else []
    with p2:
        min_score = st.slider("Score opportunité minimum", 0, 100, 0, key="dashboard_min_score")
    if selected_priorities and "priority" in filtered.columns:
        filtered = filtered[filtered["priority"].astype(str).isin(selected_priorities)]
    if "opportunity_score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["opportunity_score"], errors="coerce").fillna(0) >= min_score]

    st.markdown(f"## Opportunités à traiter — {len(filtered)}")
    cols = [c for c in [
        "priority", "opportunity_score", "company_name", "country", "employee_range", "business_theme",
        "theme_confidence", "top_signal",
    ] if c in filtered.columns]
    st.dataframe(filtered[cols] if cols else filtered, use_container_width=True, hide_index=True, height=360)

    if not filtered.empty and "company_name" in filtered.columns:
        rows = filtered.reset_index(drop=True)
        labels = [
            f"{row.get('company_name', 'Lead')} — {row.get('business_theme', 'Besoin à préciser')} — score {row.get('opportunity_score', '—')}"
            for _, row in rows.iterrows()
        ]
        selected = st.selectbox("Opportunité sélectionnée", labels, key="dashboard_selected_lead")
        lead = rows.iloc[labels.index(selected)]
        render_lead_detail(
            lead,
            contacts,
            contact_targets,
            score_field="opportunity_score",
            score_label="Score opportunité",
            signals=signals,
            events=events,
        )

    st.divider()
    _render_contacts(contacts, opportunities, discovery)
