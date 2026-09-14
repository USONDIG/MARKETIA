from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st


EMPTY_LABELS = {"", "nan", "none", "null", "inconnu", "unknown"}

NAF_GROUPS = {
    "Agriculture": {f"{n:02d}" for n in range(1, 4)},
    "Industrie": {f"{n:02d}" for n in range(5, 40)},
    "Construction": {"41", "42", "43"},
    "Commerce": {"45", "46", "47"},
    "Services": {
        "49", "50", "51", "52", "53", "55", "56", "58", "59", "60", "61", "62", "63",
        "64", "65", "66", "68", "69", "70", "71", "72", "73", "74", "75", "77", "78", "79",
        "80", "81", "82", "85", "86", "87", "88", "90", "91", "92", "93", "94", "95", "96",
    },
    "Administration publique": {"84"},
}


def safe_df(payload) -> pd.DataFrame:
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        return pd.DataFrame([payload])
    return pd.DataFrame()


def has_value(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    return text.ne("") & ~text.str.casefold().isin(EMPTY_LABELS)


def clean_values(df: pd.DataFrame, column: str) -> list[str]:
    if df.empty or column not in df.columns:
        return []
    values: list[str] = []
    for value in df[column].dropna().astype(str):
        text = value.strip()
        if text.casefold() in EMPTY_LABELS:
            continue
        if text not in values:
            values.append(text)
    return sorted(values, key=str.casefold)


def _naf_sector(value) -> str:
    raw = str(value or "").strip()
    division = raw[:2] if len(raw) >= 2 else raw.zfill(2)
    for label, divisions in NAF_GROUPS.items():
        if division in divisions:
            return label
    return "Autre / non classé"


def add_sector_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "business_sector" in df.columns:
        return df.copy()
    out = df.copy()
    if "naf" in out.columns:
        out["business_sector"] = out["naf"].map(_naf_sector)
    else:
        out["business_sector"] = "Autre / non classé"
    return out


def _sync_multiselect(key: str, options: list[str]) -> None:
    if key not in st.session_state:
        return
    current = st.session_state.get(key) or []
    st.session_state[key] = [value for value in current if value in options]


def _count_map(df: pd.DataFrame, column: str, options: list[str]) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {value: 0 for value in options}
    counts = df[column].fillna("").astype(str).value_counts().to_dict()
    return {value: int(counts.get(value, 0)) for value in options}


def _multiselect_with_counts(label: str, df: pd.DataFrame, column: str, key: str) -> list[str]:
    options = clean_values(df, column)
    _sync_multiselect(key, options)
    counts = _count_map(df, column, options)
    default = st.session_state.get(key, [])
    return st.multiselect(
        label,
        options,
        default=default,
        key=key,
        format_func=lambda value: f"{value} ({counts.get(value, 0)})",
        placeholder="Tous",
    ) if options else []


def reset_shared_filters() -> None:
    for key in [
        "marketia_country", "marketia_employee_range", "marketia_sector", "marketia_theme",
        "marketia_min_employees", "marketia_search",
    ]:
        st.session_state.pop(key, None)


def render_shared_filters(df: pd.DataFrame, *, title: str = "Périmètre actif") -> pd.DataFrame:
    base = add_sector_column(df)
    st.markdown(f"### {title}")
    st.caption("Ces filtres servent uniquement à l'affichage. Ils restent actifs entre Dashboard et Radar et ne modifient pas le ciblage du moteur.")

    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])

    scoped = base.copy()
    with c1:
        countries = _multiselect_with_counts("Pays", scoped, "country", "marketia_country")
    if countries and "country" in scoped.columns:
        scoped = scoped[scoped["country"].fillna("").astype(str).isin(countries)]

    with c2:
        employee_ranges = _multiselect_with_counts("Effectif", scoped, "employee_range", "marketia_employee_range")
    if employee_ranges and "employee_range" in scoped.columns:
        scoped = scoped[scoped["employee_range"].fillna("").astype(str).isin(employee_ranges)]

    with c3:
        sectors = _multiselect_with_counts("Secteur", scoped, "business_sector", "marketia_sector")
    if sectors and "business_sector" in scoped.columns:
        scoped = scoped[scoped["business_sector"].fillna("").astype(str).isin(sectors)]

    with c4:
        themes = _multiselect_with_counts("Besoin probable", scoped, "business_theme", "marketia_theme")
    if themes and "business_theme" in scoped.columns:
        scoped = scoped[scoped["business_theme"].fillna("").astype(str).isin(themes)]

    with c5:
        st.write("")
        st.write("")
        if st.button("Tout effacer", key="marketia_reset_filters", use_container_width=True):
            reset_shared_filters()
            st.rerun()

    d1, d2 = st.columns([1, 3])
    with d1:
        min_employees = int(st.number_input(
            "Effectif minimum connu",
            min_value=0,
            max_value=100000,
            value=int(st.session_state.get("marketia_min_employees", 0) or 0),
            step=10,
            key="marketia_min_employees",
        ))
    if min_employees > 0 and "employee_min" in scoped.columns:
        numeric = pd.to_numeric(scoped["employee_min"], errors="coerce")
        scoped = scoped[numeric >= min_employees]

    with d2:
        search = st.text_input(
            "Recherche entreprise / signal / marché / besoin",
            value=str(st.session_state.get("marketia_search", "") or ""),
            key="marketia_search",
        )
    if search:
        mask = pd.Series(False, index=scoped.index)
        for column in [
            "company_name", "business_theme", "business_theme_secondary", "markets", "top_signal",
            "top_signals", "theme_reason", "sources", "latest_title",
        ]:
            if column in scoped.columns:
                mask |= scoped[column].astype(str).str.contains(search, case=False, na=False)
        scoped = scoped[mask]

    chips: list[str] = []
    if countries:
        chips.append("Pays: " + ", ".join(countries))
    if employee_ranges:
        chips.append("Effectif: " + ", ".join(employee_ranges))
    if sectors:
        chips.append("Secteur: " + ", ".join(sectors))
    if themes:
        chips.append("Besoin: " + ", ".join(themes))
    if min_employees > 0:
        chips.append(f"≥ {min_employees} salariés")
    if search:
        chips.append(f"Recherche: {search}")
    if chips:
        st.caption("Filtres actifs — " + " · ".join(chips))

    return scoped


def match_company(df: pd.DataFrame, lead: pd.Series) -> pd.DataFrame:
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


def render_lead_detail(
    lead: pd.Series,
    contacts: pd.DataFrame,
    contact_targets: pd.DataFrame,
    *,
    score_field: str,
    score_label: str,
    signals: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
) -> None:
    st.markdown("### Fiche entreprise")
    company = str(lead.get("company_name") or "Entreprise")
    st.markdown(f"#### {company}")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.metric("Besoin probable", str(lead.get("business_theme") or "À préciser"))
    c2.metric("Confiance", f"{float(lead.get('theme_confidence') or 0):.0f} %")
    c3.metric(score_label, f"{float(lead.get(score_field) or 0):.1f}")
    c4.metric("Pays", str(lead.get("country") or "—"))

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Pourquoi MARKETIA la remonte")
        reason = str(lead.get("theme_reason") or lead.get("top_signal") or lead.get("top_signals") or "Signal à qualifier")
        st.info(reason)
        st.markdown("#### Angle commercial recommandé")
        st.write(str(lead.get("recommended_angle") or "À définir après qualification commerciale."))
        detail_rows = pd.DataFrame([
            {"Élément": "Besoins secondaires", "Détail": lead.get("business_theme_secondary")},
            {"Élément": "Fonctions à cibler", "Détail": lead.get("likely_contact_roles")},
            {"Élément": "Marchés détectés", "Détail": lead.get("markets")},
            {"Élément": "Effectif", "Détail": lead.get("employee_range")},
        ])
        st.dataframe(detail_rows, use_container_width=True, hide_index=True)

    with right:
        st.markdown("#### 👥 Contacts")
        matched_contacts = match_company(contacts, lead)
        matched_targets = match_company(contact_targets, lead)
        if not matched_contacts.empty:
            cols = [c for c in [
                "full_name", "job_title", "role_class", "linkedin_url", "professional_email",
                "professional_phone", "confidence", "source_url",
            ] if c in matched_contacts.columns]
            st.dataframe(matched_contacts[cols], use_container_width=True, hide_index=True)
        else:
            st.info("Aucun contact public suffisamment fiable identifié à ce stade.")
        if not matched_targets.empty:
            st.caption("Fonctions à rechercher / confirmer")
            cols = [c for c in ["role_class", "target_title", "relevance_score"] if c in matched_targets.columns]
            st.dataframe(matched_targets[cols].drop_duplicates(), use_container_width=True, hide_index=True)

    if signals is not None or events is not None:
        with st.expander("Signaux et preuves", expanded=False):
            s1, s2 = st.columns(2)
            company_name = str(lead.get("company_name") or "")
            with s1:
                st.caption("Signaux")
                if signals is None or signals.empty or "company_name" not in signals.columns:
                    st.info("Aucun signal détaillé disponible.")
                else:
                    rows = signals[signals["company_name"].astype(str) == company_name]
                    cols = [c for c in ["event_date", "source", "signal_type", "label", "strength", "title", "url"] if c in rows.columns]
                    st.dataframe(rows[cols] if cols else rows, use_container_width=True, hide_index=True, height=260)
            with s2:
                st.caption("Événements")
                if events is None or events.empty or "company_name" not in events.columns:
                    st.info("Aucun événement détaillé disponible.")
                else:
                    rows = events[events["company_name"].astype(str) == company_name]
                    cols = [c for c in ["event_date", "source", "event_type", "title", "detected_signals", "url"] if c in rows.columns]
                    st.dataframe(rows[cols] if cols else rows, use_container_width=True, hide_index=True, height=260)
