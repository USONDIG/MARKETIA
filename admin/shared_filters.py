from __future__ import annotations

import pandas as pd
import streamlit as st

EMPTY = {"", "nan", "none", "null", "inconnu", "unknown"}
NAF_GROUPS = {
    "Agriculture": {f"{n:02d}" for n in range(1, 4)},
    "Industrie": {f"{n:02d}" for n in range(5, 40)},
    "Construction": {"41", "42", "43"},
    "Commerce": {"45", "46", "47"},
    "Services": {"49", "50", "51", "52", "53", "55", "56", "58", "59", "60", "61", "62", "63", "64", "65", "66", "68", "69", "70", "71", "72", "73", "74", "75", "77", "78", "79", "80", "81", "82", "85", "86", "87", "88", "90", "91", "92", "93", "94", "95", "96"},
    "Administration publique": {"84"},
}


def _clean(df: pd.DataFrame, column: str) -> list[str]:
    if df.empty or column not in df.columns:
        return []
    return sorted({x.strip() for x in df[column].dropna().astype(str) if x.strip().casefold() not in EMPTY}, key=str.casefold)


def _sector(value) -> str:
    raw = str(value or "").strip(); division = raw[:2] if len(raw) >= 2 else raw.zfill(2)
    for label, values in NAF_GROUPS.items():
        if division in values:
            return label
    return "Autre / non classé"


def _commit(widget_key: str, shared_key: str) -> None:
    st.session_state[shared_key] = st.session_state.get(widget_key)
    st.session_state["marketia_filter_source"] = widget_key


def _multi(label: str, df: pd.DataFrame, column: str, name: str, prefix: str) -> list[str]:
    options = _clean(df, column)
    if not options:
        return []
    shared = f"marketia_shared_{name}"; widget = f"marketia_{prefix}_{name}"
    canonical = [x for x in (st.session_state.get(shared) or []) if x in options]
    if widget not in st.session_state or st.session_state.get("marketia_filter_source") != widget:
        st.session_state[widget] = canonical
    counts = df[column].fillna("").astype(str).value_counts().to_dict()
    return st.multiselect(label, options, key=widget, format_func=lambda x: f"{x} ({int(counts.get(x, 0))})", placeholder="Tous", on_change=_commit, args=(widget, shared))


def _number(prefix: str) -> int:
    shared = "marketia_shared_min_employees"; widget = f"marketia_{prefix}_min_employees"
    if widget not in st.session_state or st.session_state.get("marketia_filter_source") != widget:
        st.session_state[widget] = int(st.session_state.get(shared, 0) or 0)
    return int(st.number_input("Effectif minimum connu", 0, 100000, step=10, key=widget, on_change=_commit, args=(widget, shared)))


def _text(prefix: str) -> str:
    shared = "marketia_shared_search"; widget = f"marketia_{prefix}_search"
    if widget not in st.session_state or st.session_state.get("marketia_filter_source") != widget:
        st.session_state[widget] = str(st.session_state.get(shared, "") or "")
    return st.text_input("Recherche entreprise / signal / marché / besoin", key=widget, on_change=_commit, args=(widget, shared))


def reset_filters() -> None:
    for key in list(st.session_state):
        if key.startswith("marketia_shared_") or key.startswith("marketia_dashboard_") or key.startswith("marketia_radar_") or key == "marketia_filter_source":
            st.session_state.pop(key, None)


def render_filters(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    scoped = df.copy()
    if "business_sector" not in scoped.columns:
        scoped["business_sector"] = scoped["naf"].map(_sector) if "naf" in scoped.columns else "Autre / non classé"
    st.markdown("### Périmètre actif")
    st.caption("Filtres partagés entre Dashboard et Radar. Ils n'affectent pas le ciblage du moteur.")
    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
    with c1: countries = _multi("Pays", scoped, "country", "country", prefix)
    if countries and "country" in scoped.columns: scoped = scoped[scoped["country"].astype(str).isin(countries)]
    with c2: employees = _multi("Effectif", scoped, "employee_range", "employee", prefix)
    if employees and "employee_range" in scoped.columns: scoped = scoped[scoped["employee_range"].astype(str).isin(employees)]
    with c3: sectors = _multi("Secteur", scoped, "business_sector", "sector", prefix)
    if sectors: scoped = scoped[scoped["business_sector"].astype(str).isin(sectors)]
    with c4: themes = _multi("Besoin probable", scoped, "business_theme", "theme", prefix)
    if themes and "business_theme" in scoped.columns: scoped = scoped[scoped["business_theme"].astype(str).isin(themes)]
    with c5:
        st.write(""); st.write("")
        if st.button("Tout effacer", key=f"marketia_{prefix}_reset", use_container_width=True):
            reset_filters(); st.rerun()
    d1, d2 = st.columns([1, 3])
    with d1: minimum = _number(prefix)
    if minimum > 0 and "employee_min" in scoped.columns: scoped = scoped[pd.to_numeric(scoped["employee_min"], errors="coerce") >= minimum]
    with d2: search = _text(prefix)
    if search:
        mask = pd.Series(False, index=scoped.index)
        for column in ["company_name", "business_theme", "business_theme_secondary", "markets", "top_signal", "top_signals", "theme_reason", "sources", "latest_title"]:
            if column in scoped.columns: mask |= scoped[column].astype(str).str.contains(search, case=False, na=False)
        scoped = scoped[mask]
    return scoped
