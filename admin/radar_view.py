from __future__ import annotations

import pandas as pd
import streamlit as st


def safe_df(payload) -> pd.DataFrame:
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        return pd.DataFrame([payload])
    return pd.DataFrame()


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


def render_radar_discovery(load_feed, *, key_prefix: str = "radar") -> None:
    st.subheader("📡 Radar / Discovery")
    st.caption(
        "Vue large des leads détectés. Sélectionne un lead pour afficher en dessous le besoin probable, "
        "l'angle commercial et les contacts clés."
    )

    try:
        discovery = safe_df(load_feed("discovery.json"))
        stats = safe_df(load_feed("dashboard_stats.json"))
        contacts = safe_df(load_feed("contacts.json"))
        contact_targets = safe_df(load_feed("contact_targets.json"))
    except Exception as exc:
        st.error(f"Impossible de charger le Radar Discovery : {exc}")
        return

    if st.button("Actualiser Discovery", key=f"{key_prefix}_refresh"):
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
        st.info("Aucun compte Discovery disponible.")
        return

    employee_ranges = sorted(
        value for value in discovery.get("employee_range", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        if value != "Inconnu"
    )
    themes = sorted(discovery.get("business_theme", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())

    with st.expander("Filtres Discovery", expanded=True):
        a, b, c, d = st.columns(4)
        priorities = sorted(discovery.get("discovery_priority", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        statuses = sorted(discovery.get("status", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        countries = sorted(discovery.get("country", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        with a:
            selected_priorities = st.multiselect("Priorité Discovery", priorities, default=priorities, key=f"{key_prefix}_priorities")
        with b:
            selected_statuses = st.multiselect("Statut", statuses, default=statuses, key=f"{key_prefix}_statuses")
        with c:
            selected_countries = st.multiselect("Pays", countries, default=countries, key=f"{key_prefix}_countries")
        with d:
            min_score = st.slider("Score minimum", 0, 100, 0, key=f"{key_prefix}_score")

        e, f, g, h = st.columns([2, 2, 2, 3])
        with e:
            selected_employee_ranges = st.multiselect(
                "Tranches d'effectif", employee_ranges, default=employee_ranges, key=f"{key_prefix}_employees"
            )
        with f:
            min_employees = int(st.number_input(
                "Effectif minimum connu", min_value=0, max_value=100000, value=0, step=10,
                key=f"{key_prefix}_min_employees",
            ))
        with g:
            selected_themes = st.multiselect("Besoin probable", themes, default=themes, key=f"{key_prefix}_themes")
        with h:
            search = st.text_input("Entreprise / signal / marché / besoin", "", key=f"{key_prefix}_search")

    filtered = discovery.copy()
    if selected_priorities and "discovery_priority" in filtered.columns:
        filtered = filtered[filtered["discovery_priority"].isin(selected_priorities)]
    if selected_statuses and "status" in filtered.columns:
        filtered = filtered[filtered["status"].isin(selected_statuses)]
    if selected_countries and "country" in filtered.columns:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if selected_themes and "business_theme" in filtered.columns:
        filtered = filtered[filtered["business_theme"].isin(selected_themes)]
    if "discovery_score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["discovery_score"], errors="coerce").fillna(0) >= min_score]
    if "employee_range" in filtered.columns and selected_employee_ranges:
        known_mask = filtered["employee_range"].isin(selected_employee_ranges)
        unknown_mask = filtered["employee_range"].fillna("Inconnu").eq("Inconnu")
        filtered = filtered[known_mask | unknown_mask]
    if min_employees > 0 and "employee_min" in filtered.columns:
        numeric = pd.to_numeric(filtered["employee_min"], errors="coerce")
        filtered = filtered[numeric >= min_employees]
    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ["company_name", "markets", "top_signals", "sources", "business_theme", "theme_reason"]:
            if column in filtered.columns:
                mask |= filtered[column].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    st.markdown(f"### Leads détectés — {len(filtered)}")
    preferred = [
        "discovery_priority", "discovery_score", "status", "company_name", "country", "employee_range",
        "business_theme", "theme_confidence", "markets", "top_signals", "latest_event_date",
    ]
    columns = [column for column in preferred if column in filtered.columns]
    st.dataframe(filtered[columns] if columns else filtered, use_container_width=True, hide_index=True, height=460)

    if filtered.empty or "company_name" not in filtered.columns:
        return

    labels: list[str] = []
    index_by_label: dict[str, int] = {}
    for idx, row in filtered.reset_index(drop=True).iterrows():
        label = f"{row.get('company_name', 'Lead')} — score {row.get('discovery_score', '—')} — {row.get('business_theme', 'Besoin à préciser')}"
        if label in index_by_label:
            label = f"{label} #{idx + 1}"
        labels.append(label)
        index_by_label[label] = idx

    st.divider()
    st.markdown("### Détail du lead")
    selected_label = st.selectbox("Lead sélectionné", labels, key=f"{key_prefix}_selected_lead")
    lead = filtered.reset_index(drop=True).iloc[index_by_label[selected_label]]

    c1, c2, c3 = st.columns([2, 1, 1])
    c1.metric("Besoin probable", str(lead.get("business_theme") or "À préciser"))
    c2.metric("Confiance", f"{float(lead.get('theme_confidence') or 0):.0f} %")
    c3.metric("Score Discovery", f"{float(lead.get('discovery_score') or 0):.1f}")

    detail_rows = pd.DataFrame([
        {"Élément": "Besoin principal", "Détail": lead.get("business_theme")},
        {"Élément": "Besoins secondaires", "Détail": lead.get("business_theme_secondary")},
        {"Élément": "Pourquoi", "Détail": lead.get("theme_reason")},
        {"Élément": "Angle commercial recommandé", "Détail": lead.get("recommended_angle")},
        {"Élément": "Fonctions à cibler", "Détail": lead.get("likely_contact_roles")},
        {"Élément": "Marchés détectés", "Détail": lead.get("markets")},
        {"Élément": "Signaux principaux", "Détail": lead.get("top_signals")},
        {"Élément": "Dernier événement", "Détail": lead.get("latest_title")},
    ])
    st.dataframe(detail_rows, use_container_width=True, hide_index=True)

    st.markdown("#### 👥 Contacts clés")
    matched_contacts = _match_company(contacts, lead)
    matched_targets = _match_company(contact_targets, lead)

    if not matched_contacts.empty:
        contact_cols = [
            c for c in ["full_name", "job_title", "role_class", "confidence", "professional_email",
                        "professional_phone", "source_name", "source_url", "verified_at"]
            if c in matched_contacts.columns
        ]
        st.dataframe(matched_contacts[contact_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Aucun contact public suffisamment fiable n'a encore été identifié pour ce lead.")

    if not matched_targets.empty:
        st.caption("Fonctions prioritaires encore à rechercher / confirmer")
        target_cols = [c for c in ["role_class", "target_title", "relevance_score", "preferred_sources"] if c in matched_targets.columns]
        st.dataframe(matched_targets[target_cols].drop_duplicates(), use_container_width=True, hide_index=True)

    st.info(
        "Les contacts automatiques proviennent de sources web publiques. LinkedIn peut rester une source de vérification manuelle "
        "ou être connecté ultérieurement via un accès/API autorisé ; MARKETIA ne scrape pas directement LinkedIn."
    )
