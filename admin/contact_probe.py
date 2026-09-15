from __future__ import annotations

import pandas as pd
import streamlit as st

from contact_api_client import persist_contacts_to_github, search_contacts

DEFAULT_CONTACT_API_URL = "https://marketia-contact-api.onrender.com"


def _display_contacts(contacts: list[dict]) -> None:
    if not contacts:
        st.warning("Aucun contact qualifié trouvé pour cette entreprise.")
        return

    rows = []
    for contact in contacts:
        rows.append({
            "Nom": contact.get("full_name"),
            "Fonction": contact.get("job_title"),
            "Rôle": contact.get("role_class"),
            "Score": contact.get("relevance_score"),
            "LinkedIn": contact.get("linkedin_url"),
            "Source": contact.get("source_name"),
            "Preuve": contact.get("evidence_summary"),
        })
    frame = pd.DataFrame(rows)
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "LinkedIn": st.column_config.LinkColumn("LinkedIn"),
            "Score": st.column_config.NumberColumn("Score", format="%d"),
        },
    )


def render_contact_probe(default_company: str = "XPO Logistics") -> None:
    st.markdown("### Recherche contacts à la demande")
    st.caption(
        "La recherche suit automatiquement l'entreprise sélectionnée dans le Dashboard. Elle est exécutée par l'API MARKETIA sur Render, puis les contacts qualifiés sont sauvegardés sur la branche GitHub data/contact-results. Aucun workflow MARKETIA complet n'est lancé."
    )

    api_url = str(st.secrets.get("contact_api_url", DEFAULT_CONTACT_API_URL)).strip()
    github_token = str(st.secrets.get("github_token", "")).strip()

    selected_company = str(default_company or "").strip()
    previous_selected = str(st.session_state.get("contact_probe_selected_company") or "").strip()
    if selected_company and selected_company != previous_selected:
        st.session_state["contact_probe_selected_company"] = selected_company
        st.session_state["contact_probe_company"] = selected_company
        st.session_state.pop("contact_probe_payload", None)
        st.session_state.pop("contact_probe_persistence", None)
        st.session_state.pop("contact_probe_last_company", None)

    if "contact_probe_company" not in st.session_state:
        st.session_state["contact_probe_company"] = selected_company or "XPO Logistics"

    company = st.text_input(
        "Entreprise sélectionnée",
        key="contact_probe_company",
        help="Le nom suit automatiquement l'opportunité sélectionnée. Tu peux l'ajuster manuellement avant de lancer la recherche.",
    )

    if st.button("Rechercher les contacts maintenant", type="primary", key="contact_probe_run"):
        company_to_search = company.strip()
        with st.spinner(f"Recherche et qualification des contacts pour {company_to_search}…"):
            try:
                payload = search_contacts(api_url, company_to_search, timeout=45)
            except Exception as exc:
                st.error(f"Recherche contacts impossible : {exc}")
                return

        contacts = payload.get("contacts") or []
        st.session_state["contact_probe_payload"] = payload
        st.session_state["contact_probe_last_company"] = company_to_search

        if contacts and github_token:
            try:
                persistence = persist_contacts_to_github(github_token, contacts)
                st.session_state["contact_probe_persistence"] = persistence
            except Exception as exc:
                st.session_state["contact_probe_persistence"] = {"error": str(exc)}
        elif contacts:
            st.session_state["contact_probe_persistence"] = {"error": "github_token absent"}

    payload = st.session_state.get("contact_probe_payload")
    if not isinstance(payload, dict):
        return

    contacts = payload.get("contacts") or []
    providers = ", ".join(payload.get("providers") or []) or "-"
    a, b, c = st.columns(3)
    a.metric("Contacts qualifiés", int(payload.get("qualified_count") or len(contacts)))
    b.metric("Résultats bruts", int(payload.get("raw_result_count") or 0))
    c.metric("Source", providers)

    _display_contacts(contacts)

    persistence = st.session_state.get("contact_probe_persistence")
    if isinstance(persistence, dict):
        if persistence.get("error"):
            st.warning(f"Contacts trouvés, mais sauvegarde GitHub non effectuée : {persistence['error']}")
        elif persistence.get("commit_sha"):
            st.success(
                f"Contacts sauvegardés sur GitHub ({persistence.get('branch')}) — {persistence.get('after')} contact(s) dans le référentiel."
            )
