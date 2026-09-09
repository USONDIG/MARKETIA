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


def render_qualified_dashboard(load_feed, render_run_status) -> None:
    st.subheader("Dashboard MARKETIA")
    st.caption("Vue des opportunités qualifiées, avec besoin probable, justification commerciale et contacts clés.")
    render_run_status()

    try:
        stats = safe_df(load_feed("dashboard_stats.json"))
        opportunities = safe_df(load_feed("opportunities.json"))
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

    if opportunities.empty:
        st.info("Aucune opportunité qualifiée pour le moment. Consulte Radar / Discovery pour voir les leads en cours d'identification.")
        return

    base = opportunities.copy()
    priorities = _clean_values(base.get("priority", pd.Series(dtype=str)))
    countries = _clean_values(base.get("country", pd.Series(dtype=str)))
    employee_ranges = _clean_values(base.get("employee_range", pd.Series(dtype=str)))
    themes = _clean_values(base.get("business_theme", pd.Series(dtype=str)))

    with st.expander("Filtres opportunités", expanded=True):
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
            selected_employee_ranges = st.multiselect(
                "Tranches d'effectif", employee_ranges, default=employee_ranges, key="dash_employee_ranges"
            ) if employee_ranges else []
        with f:
            min_employees = int(st.number_input(
                "Effectif minimum connu", min_value=0, max_value=100000, value=0, step=10, key="dash_min_employees"
            ))
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

    st.markdown(f"### Opportunités qualifiées — {len(filtered)}")
    preferred = [
        "priority", "opportunity_score", "company_name", "country", "employee_range",
        "business_theme", "theme_confidence", "infra_fit", "buying_intent", "timing", "top_signal",
    ]
    columns = [column for column in preferred if column in filtered.columns]
    st.dataframe(filtered[columns] if columns else filtered, use_container_width=True, hide_index=True, height=420)

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
        contact_cols = [
            col for col in ["full_name", "job_title", "role_class", "confidence", "linkedin_url",
                            "professional_email", "professional_phone", "source_name", "source_url", "verified_at"]
            if col in matched_contacts.columns
        ]
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
