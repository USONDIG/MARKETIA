from __future__ import annotations

import pandas as pd
import streamlit as st


def safe_df(payload) -> pd.DataFrame:
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        return pd.DataFrame([payload])
    return pd.DataFrame()


def _clean_values(series: pd.Series) -> list[str]:
    if series.empty:
        return []
    invalid = {"", "nan", "none", "null", "unknown", "inconnu"}
    values = []
    for value in series.dropna().astype(str):
        text = value.strip()
        if text.casefold() not in invalid:
            values.append(text)
    return sorted(set(values))


def _has_value(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("") & ~series.fillna("").astype(str).str.casefold().isin({"nan", "none", "null"})


def _match_company(df: pd.DataFrame, lead: pd.Series) -> pd.DataFrame:
    if df.empty:
        return df
    siren = str(lead.get("siren") or "").strip()
    name = str(lead.get("company_name") or "").strip()
    if siren and "siren" in df.columns:
        matched = df[df["siren"].fillna("").astype(str) == siren]
        if not matched.empty:
            return matched
    if name and "company_name" in df.columns:
        return df[df["company_name"].fillna("").astype(str).str.casefold() == name.casefold()]
    return df.iloc[0:0]


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
            "theme_confidence": row.get("theme_confidence"),
            "country": row.get("country"),
            "employee_range": row.get("employee_range"),
            "recommended_angle": row.get("recommended_angle"),
        }
    for _, row in opportunities.iterrows():
        metadata[_lead_key(row)] = {
            "lead_status": "QUALIFIED",
            "score": row.get("opportunity_score"),
            "priority": row.get("priority"),
            "business_theme": row.get("business_theme"),
            "theme_confidence": row.get("theme_confidence"),
            "country": row.get("country"),
            "employee_range": row.get("employee_range"),
            "recommended_angle": row.get("recommended_angle"),
        }

    rows: list[dict] = []
    for _, contact in contacts.iterrows():
        meta = metadata.get(_lead_key(contact), {})
        rows.append({
            "lead_status": meta.get("lead_status", "CONTACT_ONLY"),
            "priority": meta.get("priority"),
            "score": meta.get("score"),
            "company_name": contact.get("company_name"),
            "country": meta.get("country"),
            "employee_range": meta.get("employee_range"),
            "business_theme": meta.get("business_theme"),
            "theme_confidence": meta.get("theme_confidence"),
            "full_name": contact.get("full_name"),
            "job_title": contact.get("job_title"),
            "role_class": contact.get("role_class"),
            "linkedin_url": contact.get("linkedin_url"),
            "professional_email": contact.get("professional_email"),
            "professional_phone": contact.get("professional_phone"),
            "confidence": contact.get("confidence"),
            "source_name": contact.get("source_name"),
            "source_url": contact.get("source_url"),
            "recommended_angle": meta.get("recommended_angle"),
            "siren": contact.get("siren"),
        })
    return pd.DataFrame(rows)


def _render_contacts_table(contacts: pd.DataFrame, opportunities: pd.DataFrame, discovery: pd.DataFrame) -> None:
    st.markdown("## 👥 Contacts trouvés — opportunités actionnables")
    st.caption("Uniquement les leads pour lesquels MARKETIA a identifié au moins une personne. Cette vue sert de liste d'action commerciale.")

    actionable = _build_actionable_contacts(contacts, opportunities, discovery)
    if actionable.empty:
        st.warning("Aucun contact nominatif n'est actuellement disponible. La recherche contacts continuera aux prochains runs.")
        return

    linkedin_mask = _has_value(actionable.get("linkedin_url", pd.Series(index=actionable.index, dtype=str)))
    email_mask = _has_value(actionable.get("professional_email", pd.Series(index=actionable.index, dtype=str)))
    phone_mask = _has_value(actionable.get("professional_phone", pd.Series(index=actionable.index, dtype=str)))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contacts", len(actionable))
    c2.metric("Avec LinkedIn", int(linkedin_mask.sum()))
    c3.metric("Avec email pro", int(email_mask.sum()))
    c4.metric("Avec téléphone", int(phone_mask.sum()))

    roles = _clean_values(actionable.get("role_class", pd.Series(dtype=str)))
    themes = _clean_values(actionable.get("business_theme", pd.Series(dtype=str)))
    countries = _clean_values(actionable.get("country", pd.Series(dtype=str)))
    statuses = _clean_values(actionable.get("lead_status", pd.Series(dtype=str)))

    availability_options = []
    if linkedin_mask.any():
        availability_options.append("LinkedIn")
    if email_mask.any():
        availability_options.append("Email pro")
    if phone_mask.any():
        availability_options.append("Téléphone")

    with st.expander("Filtres contacts", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            selected_availability = st.multiselect("Coordonnée disponible", availability_options, default=[], key="contacts_availability") if availability_options else []
        with f2:
            selected_roles = st.multiselect("Type de contact", roles, default=roles, key="contacts_roles") if roles else []
        with f3:
            selected_statuses = st.multiselect("Maturité du lead", statuses, default=statuses, key="contacts_status") if statuses else []
        with f4:
            min_score = st.slider("Score minimum", 0, 100, 0, key="contacts_score")

        f5, f6, f7 = st.columns([2, 2, 3])
        with f5:
            selected_themes = st.multiselect("Besoin probable", themes, default=themes, key="contacts_themes") if themes else []
        with f6:
            selected_countries = st.multiselect("Pays", countries, default=countries, key="contacts_countries") if countries else []
        with f7:
            search = st.text_input("Entreprise / contact / fonction", "", key="contacts_search")

    filtered = actionable.copy()
    if selected_roles and "role_class" in filtered.columns:
        filtered = filtered[filtered["role_class"].isin(selected_roles)]
    if selected_statuses and "lead_status" in filtered.columns:
        filtered = filtered[filtered["lead_status"].isin(selected_statuses)]
    if selected_themes and "business_theme" in filtered.columns:
        filtered = filtered[filtered["business_theme"].isin(selected_themes)]
    if selected_countries and "country" in filtered.columns:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if "score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["score"], errors="coerce").fillna(0) >= min_score]

    if selected_availability:
        available = pd.Series(True, index=filtered.index)
        if "LinkedIn" in selected_availability:
            available &= _has_value(filtered.get("linkedin_url", pd.Series(index=filtered.index, dtype=str)))
        if "Email pro" in selected_availability:
            available &= _has_value(filtered.get("professional_email", pd.Series(index=filtered.index, dtype=str)))
        if "Téléphone" in selected_availability:
            available &= _has_value(filtered.get("professional_phone", pd.Series(index=filtered.index, dtype=str)))
        filtered = filtered[available]

    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ["company_name", "full_name", "job_title", "business_theme"]:
            if column in filtered.columns:
                mask |= filtered[column].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    st.caption(f"{len(filtered)} contact(s) exploitable(s) après filtrage")
    display_cols = [
        "lead_status", "priority", "score", "company_name", "country", "business_theme",
        "full_name", "job_title", "role_class", "linkedin_url", "professional_email",
        "professional_phone", "confidence", "source_url",
    ]
    display_cols = [col for col in display_cols if col in filtered.columns]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True, height=360)

    if not filtered.empty:
        labels = []
        by_label = {}
        for idx, row in filtered.reset_index(drop=True).iterrows():
            label = f"{row.get('company_name', 'Lead')} — {row.get('full_name', 'Contact')} — {row.get('job_title', '')}"
            if label in by_label:
                label = f"{label} #{idx + 1}"
            labels.append(label)
            by_label[label] = idx
        selected = st.selectbox("Contact à traiter", labels, key="selected_actionable_contact")
        row = filtered.reset_index(drop=True).iloc[by_label[selected]]
        d1, d2, d3 = st.columns(3)
        d1.metric("Entreprise", str(row.get("company_name") or "—"))
        d2.metric("Besoin", str(row.get("business_theme") or "À qualifier"))
        d3.metric("Score", f"{float(row.get('score') or 0):.1f}")
        details = pd.DataFrame([
            {"Élément": "Contact", "Détail": row.get("full_name")},
            {"Élément": "Fonction", "Détail": row.get("job_title")},
            {"Élément": "LinkedIn", "Détail": row.get("linkedin_url")},
            {"Élément": "Email pro", "Détail": row.get("professional_email")},
            {"Élément": "Téléphone", "Détail": row.get("professional_phone")},
            {"Élément": "Angle commercial", "Détail": row.get("recommended_angle")},
            {"Élément": "Source", "Détail": row.get("source_url")},
        ])
        st.dataframe(details, use_container_width=True, hide_index=True)

    st.divider()


def render_qualified_dashboard(load_feed, render_run_status) -> None:
    st.subheader("Dashboard MARKETIA")
    st.caption("Vue des opportunités qualifiées, avec besoin probable, justification commerciale et contacts clés.")
    render_run_status()

    try:
        stats = safe_df(load_feed("dashboard_stats.json"))
        opportunities = safe_df(load_feed("opportunities.json"))
        discovery = safe_df(load_feed("discovery.json"))
        signals = safe_df(load_feed("signals.json"))
        events = safe_df(load_feed("events.json"))
        market_summary = safe_df(load_feed("market_summary.json"))
        country_summary = safe_df(load_feed("country_summary.json"))
        source_summary = safe_df(load_feed("source_summary.json"))
        contacts = safe_df(load_feed("contacts.json"))
        contact_targets = safe_df(load_feed("contact_targets.json"))
    except Exception as exc:
        st.error(f"Impossible de charger les flux MARKETIA : {exc}")
        return

    if not stats.empty:
        row = stats.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("CRITICAL", int(row.get("critical", 0) or 0))
        c2.metric("HOT", int(row.get("hot", 0) or 0))
        c3.metric("WARM", int(row.get("warm", 0) or 0))
        c4.metric("Opportunités", int(row.get("opportunities", 0) or 0))
        c5.metric("Score moyen", f"{float(row.get('avg_score', 0) or 0):.1f}")

    _render_contacts_table(contacts, opportunities, discovery)

    if opportunities.empty:
        st.info("Aucune opportunité qualifiée pour le moment. Consulte Radar / Discovery pour voir les leads en cours d'identification.")
        return

    base = opportunities.copy()
    priorities = _clean_values(base.get("priority", pd.Series(dtype=str)))
    countries = _clean_values(base.get("country", pd.Series(dtype=str)))
    employee_ranges = _clean_values(base.get("employee_range", pd.Series(dtype=str)))
    themes = _clean_values(base.get("business_theme", pd.Series(dtype=str)))

    with st.expander("Filtres opportunités", expanded=False):
        a, b, c, d = st.columns(4)
        with a:
            selected_priorities = st.multiselect("Priorité", priorities, default=priorities, key="dash_priorities")
        with b:
            selected_countries = st.multiselect("Pays", countries, default=countries, key="dash_countries") if countries else []
        with c:
            min_score = st.slider("Score minimum", 0, 100, 0, key="dash_score")
        with d:
            selected_themes = st.multiselect("Besoin probable", themes, default=themes, key="dash_themes") if themes else []

        e, f, g = st.columns([2, 2, 3])
        with e:
            selected_employee_ranges = st.multiselect("Tranches d'effectif", employee_ranges, default=employee_ranges, key="dash_employee_ranges") if employee_ranges else []
        with f:
            min_employees = int(st.number_input("Effectif minimum connu", min_value=0, max_value=100000, value=0, step=10, key="dash_min_employees"))
        with g:
            search = st.text_input("Entreprise / signal / marché / besoin", "", key="dash_search")

    filtered = base.copy()
    if selected_priorities and "priority" in filtered.columns:
        filtered = filtered[filtered["priority"].isin(selected_priorities)]
    if selected_countries and "country" in filtered.columns:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if selected_themes and "business_theme" in filtered.columns:
        filtered = filtered[filtered["business_theme"].isin(selected_themes)]
    if "opportunity_score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["opportunity_score"], errors="coerce").fillna(0) >= min_score]
    if selected_employee_ranges and "employee_range" in filtered.columns:
        filtered = filtered[filtered["employee_range"].isin(selected_employee_ranges)]
    if min_employees > 0 and "employee_min" in filtered.columns:
        numeric = pd.to_numeric(filtered["employee_min"], errors="coerce")
        filtered = filtered[numeric >= min_employees]
    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ["company_name", "business_theme", "business_theme_secondary", "top_signal", "markets", "theme_reason"]:
            if column in filtered.columns:
                mask |= filtered[column].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    st.markdown(f"### Toutes les opportunités qualifiées — {len(filtered)}")
    preferred = [
        "priority", "opportunity_score", "company_name", "country", "employee_range",
        "business_theme", "theme_confidence", "infra_fit", "buying_intent", "timing", "top_signal",
    ]
    columns = [column for column in preferred if column in filtered.columns]
    st.dataframe(filtered[columns] if columns else filtered, use_container_width=True, hide_index=True, height=360)

    if filtered.empty or "company_name" not in filtered.columns:
        return

    labels: list[str] = []
    index_by_label: dict[str, int] = {}
    rows = filtered.reset_index(drop=True)
    for idx, lead in rows.iterrows():
        label = f"{lead.get('company_name', 'Lead')} — score {lead.get('opportunity_score', '—')} — {lead.get('business_theme', 'Besoin à préciser')}"
        if label in index_by_label:
            label = f"{label} #{idx + 1}"
        labels.append(label)
        index_by_label[label] = idx

    st.divider()
    st.markdown("### Détail de l'opportunité")
    selected_label = st.selectbox("Lead sélectionné", labels, key="dash_selected_lead")
    lead = rows.iloc[index_by_label[selected_label]]

    c1, c2, c3 = st.columns([2, 1, 1])
    c1.metric("Besoin probable", str(lead.get("business_theme") or "À préciser"))
    c2.metric("Confiance", f"{float(lead.get('theme_confidence') or 0):.0f} %")
    c3.metric("Score opportunité", f"{float(lead.get('opportunity_score') or 0):.1f}")

    detail_rows = pd.DataFrame([
        {"Élément": "Besoin principal", "Détail": lead.get("business_theme")},
        {"Élément": "Besoins secondaires", "Détail": lead.get("business_theme_secondary")},
        {"Élément": "Pourquoi", "Détail": lead.get("theme_reason")},
        {"Élément": "Angle commercial recommandé", "Détail": lead.get("recommended_angle")},
        {"Élément": "Fonctions à cibler", "Détail": lead.get("likely_contact_roles")},
        {"Élément": "Signal principal", "Détail": lead.get("top_signal")},
        {"Élément": "Marchés détectés", "Détail": lead.get("markets")},
    ])
    st.dataframe(detail_rows, use_container_width=True, hide_index=True)

    st.markdown("#### 👥 Contacts clés")
    matched_contacts = _match_company(contacts, lead)
    matched_targets = _match_company(contact_targets, lead)
    if not matched_contacts.empty:
        contact_cols = [col for col in ["full_name", "job_title", "role_class", "confidence", "linkedin_url", "professional_email", "professional_phone", "source_name", "source_url", "verified_at"] if col in matched_contacts.columns]
        st.dataframe(matched_contacts[contact_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Aucun contact suffisamment fiable n'a encore été identifié pour cette opportunité.")

    if not matched_targets.empty:
        st.caption("Fonctions prioritaires encore à rechercher / confirmer")
        target_cols = [col for col in ["role_class", "target_title", "relevance_score", "preferred_sources"] if col in matched_targets.columns]
        st.dataframe(matched_targets[target_cols].drop_duplicates(), use_container_width=True, hide_index=True)

    st.markdown("### Pourquoi maintenant ?")
    company_name = str(lead.get("company_name") or "")
    company_signals = signals[signals["company_name"].astype(str) == company_name] if not signals.empty and "company_name" in signals.columns else pd.DataFrame()
    company_events = events[events["company_name"].astype(str) == company_name] if not events.empty and "company_name" in events.columns else pd.DataFrame()
    s1, s2 = st.columns(2)
    with s1:
        st.caption("Signaux")
        cols = [col for col in ["event_date", "source", "signal_type", "label", "strength", "title", "url"] if col in company_signals.columns]
        if company_signals.empty:
            st.info("Aucun signal détaillé disponible.")
        else:
            st.dataframe(company_signals[cols] if cols else company_signals, use_container_width=True, hide_index=True, height=300)
    with s2:
        st.caption("Événements")
        cols = [col for col in ["event_date", "source", "event_type", "title", "detected_signals", "url"] if col in company_events.columns]
        if company_events.empty:
            st.info("Aucun événement détaillé disponible.")
        else:
            st.dataframe(company_events[cols] if cols else company_events, use_container_width=True, hide_index=True, height=300)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### Répartition par pays")
        if not country_summary.empty and {"country", "opportunities"}.issubset(country_summary.columns):
            st.bar_chart(country_summary[["country", "opportunities"]].dropna().set_index("country"))
    with c2:
        st.markdown("#### Signaux par marché")
        if not market_summary.empty and {"label", "count"}.issubset(market_summary.columns):
            st.bar_chart(market_summary[["label", "count"]].set_index("label"))
    with c3:
        st.markdown("#### Événements par source")
        if not source_summary.empty and {"source", "count"}.issubset(source_summary.columns):
            st.bar_chart(source_summary[["source", "count"]].set_index("source"))
