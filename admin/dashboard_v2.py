from __future__ import annotations

import re
import unicodedata

import pandas as pd
import streamlit as st

from contact_probe import render_contact_probe
from shared_filters import render_filters
from shared_ui import clean_values, has_value, render_lead_detail, safe_df


_GENERIC_COMPANY_WORDS = {
    "france", "europe", "centre", "center", "distribution", "logistics", "logistique",
    "sas", "sasu", "sa", "se", "holding", "groupe", "group", "international",
}


def _norm_company(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _company_aliases(value: str) -> set[str]:
    raw = str(value or "").strip()
    if not raw:
        return set()
    aliases: set[str] = set()
    for segment in re.split(r"[,;/|]", raw):
        norm = _norm_company(segment)
        if not norm:
            continue
        aliases.add(norm)
        tokens = norm.split()
        trimmed = list(tokens)
        while len(trimmed) > 2 and trimmed[-1] in _GENERIC_COMPANY_WORDS:
            trimmed.pop()
        if trimmed:
            aliases.add(" ".join(trimmed))
        meaningful = [tok for tok in tokens if tok not in _GENERIC_COMPANY_WORDS]
        if len(meaningful) >= 2:
            aliases.add(" ".join(meaningful[:2]))
        elif meaningful:
            aliases.add(meaningful[0])
    return {alias for alias in aliases if len(alias) >= 3}


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
            "siren": contact.get("siren"),
            "priority": extra.get("priority"),
            "score": extra.get("score"),
            "company_name": contact.get("company_name"),
            "business_theme": extra.get("business_theme"),
            "full_name": contact.get("full_name"),
            "job_title": contact.get("job_title"),
            "role_class": contact.get("role_class"),
            "linkedin_url": contact.get("linkedin_url"),
            "professional_email": contact.get("professional_email"),
            "professional_phone": contact.get("professional_phone"),
            "confidence": contact.get("confidence"),
            "status": contact.get("status"),
            "role_evidence": contact.get("role_evidence"),
            "linkedin_status": contact.get("linkedin_status"),
            "email_status": contact.get("email_status"),
            "phone_status": contact.get("phone_status"),
            "phone_type": contact.get("phone_type"),
            "phone_source_url": contact.get("phone_source_url"),
            "phone_evidence": contact.get("phone_evidence"),
            "evidence_summary": contact.get("evidence_summary"),
            "source_url": contact.get("source_url"),
        })
    return pd.DataFrame(rows)


def _contacts_for_lead(contacts: pd.DataFrame, lead: pd.Series) -> pd.DataFrame:
    if contacts.empty:
        return contacts
    siren = str(lead.get("siren") or "").strip()
    company = str(lead.get("company_name") or "").strip()

    if siren and "siren" in contacts.columns:
        contact_sirens = contacts["siren"].fillna("").astype(str).str.strip()
        match = contacts[contact_sirens == siren]
        if not match.empty:
            return match

    if company and "company_name" in contacts.columns:
        names = contacts["company_name"].fillna("").astype(str)
        company_norm = _norm_company(company)
        exact = contacts[names.map(_norm_company) == company_norm]
        if not exact.empty:
            return exact

        lead_aliases = _company_aliases(company)
        alias_mask = names.map(lambda value: bool(lead_aliases & _company_aliases(value)))
        alias_match = contacts[alias_mask]
        if not alias_match.empty:
            return alias_match

    return contacts.iloc[0:0]


def _render_context_contacts(contacts: pd.DataFrame, lead: pd.Series) -> None:
    company = str(lead.get("company_name") or "Entreprise")
    siren = str(lead.get("siren") or "").strip()
    st.divider()
    st.markdown(f"## 👥 Contacts associés à {company}")
    st.caption("Contacts reliés à l'entreprise sélectionnée. Les coordonnées ne sont affichées comme confirmées que lorsqu'elles existent dans les données MARKETIA.")

    matched = _contacts_for_lead(contacts, lead)
    if matched.empty:
        st.info("Aucun contact sauvegardé pour cette entreprise. Lance la recherche à la demande ci-dessous.")
    else:
        linkedin = has_value(matched.get("linkedin_url", pd.Series(index=matched.index, dtype=str)))
        email = has_value(matched.get("professional_email", pd.Series(index=matched.index, dtype=str)))
        phone = has_value(matched.get("professional_phone", pd.Series(index=matched.index, dtype=str)))
        a, b, c, d = st.columns(4)
        a.metric("Contacts", len(matched))
        b.metric("LinkedIn", int(linkedin.sum()))
        c.metric("Email pro", int(email.sum()))
        d.metric("Téléphone", int(phone.sum()))

        display = matched.copy()
        if "confidence" in display.columns:
            display["confidence"] = pd.to_numeric(display["confidence"], errors="coerce").round(0)
        cols = [c for c in [
            "full_name", "job_title", "role_class", "linkedin_url", "professional_email",
            "professional_phone", "phone_status", "phone_type", "confidence", "status",
            "role_evidence", "linkedin_status", "email_status", "phone_source_url",
            "phone_evidence", "evidence_summary", "source_url",
        ] if c in display.columns]
        st.dataframe(display[cols] if cols else display, use_container_width=True, hide_index=True, height=min(420, 80 + 38 * max(1, len(display))))

    render_contact_probe(company, existing_contacts=matched.to_dict("records"), siren=siren)


def render_dashboard(load_feed, render_run_status) -> None:
    st.subheader("Dashboard")
    st.caption("Que dois-je traiter maintenant ? Opportunités qualifiées, contacts disponibles et contexte commercial.")
    render_run_status(compact=True)
    try:
        stats = safe_df(load_feed("dashboard_stats.json")); opportunities = safe_df(load_feed("opportunities.json")); discovery = safe_df(load_feed("discovery.json"))
        signals = safe_df(load_feed("signals.json")); events = safe_df(load_feed("events.json")); contacts = safe_df(load_feed("contacts.json")); targets = safe_df(load_feed("contact_targets.json"))
    except Exception as exc:
        st.error(f"Impossible de charger les flux MARKETIA : {exc}"); return

    row = stats.iloc[0] if not stats.empty else pd.Series(dtype=object)
    actionable = _contacts_view(contacts, opportunities, discovery)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Opportunités", int(row.get("opportunities", len(opportunities)) or 0))
    m2.metric("À contacter", len(actionable))
    m3.metric("HOT / WARM", int(row.get("hot", 0) or 0) + int(row.get("warm", 0) or 0))
    m4.metric("Leads Radar", int(row.get("discovery_medium", 0) or 0) + int(row.get("discovery_high", 0) or 0))
    m5.metric("Score moyen", f"{float(row.get('avg_score', 0) or 0):.1f}")

    if opportunities.empty:
        st.info("Aucune opportunité qualifiée pour le moment. Consulte Radar / Discovery pour les leads émergents.")
        return

    filtered = render_filters(opportunities, "dashboard")
    a, b = st.columns([2, 1])
    with a:
        priorities = clean_values(filtered, "priority")
        selected = st.multiselect("Priorité commerciale", priorities, key="dashboard_priority_v2", placeholder="Toutes") if priorities else []
    with b:
        minimum = st.slider("Score opportunité minimum", 0, 100, 0, key="dashboard_score_v2")
    if selected and "priority" in filtered.columns:
        filtered = filtered[filtered["priority"].astype(str).isin(selected)]
    if "opportunity_score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["opportunity_score"], errors="coerce").fillna(0) >= minimum]

    st.markdown(f"## Opportunités à traiter — {len(filtered)}")
    cols = [c for c in [
        "priority", "opportunity_score", "company_name", "country", "employee_range",
        "business_theme", "theme_confidence", "top_signal",
    ] if c in filtered.columns]
    st.dataframe(filtered[cols] if cols else filtered, use_container_width=True, hide_index=True, height=360)

    selected_lead = None
    if not filtered.empty and "company_name" in filtered.columns:
        rows = filtered.reset_index(drop=True)
        labels = [f"{r.get('company_name', 'Lead')} — {r.get('business_theme', 'Besoin à préciser')} — score {r.get('opportunity_score', '—')}" for _, r in rows.iterrows()]
        choice = st.selectbox("Opportunité sélectionnée", labels, key="dashboard_lead_v2")
        selected_lead = rows.iloc[labels.index(choice)]
        render_lead_detail(selected_lead, contacts, targets, score_field="opportunity_score", score_label="Score opportunité", signals=signals, events=events)

    if selected_lead is not None:
        _render_context_contacts(contacts, selected_lead)
