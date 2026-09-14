from __future__ import annotations

from copy import deepcopy

import streamlit as st
import yaml

from app_services import load_config, load_workflow_runs, save_config

COUNTRIES = ["FR", "BE", "DE", "NL", "ES", "IT", "LU", "AT", "PT", "IE", "DK", "SE", "FI", "PL", "CZ"]
NAF_GROUPS = {
    "Agriculture": [f"{n:02d}" for n in range(1, 4)],
    "Industrie": [f"{n:02d}" for n in range(5, 40)],
    "Construction": ["41", "42", "43"],
    "Commerce": ["45", "46", "47"],
    "Services": ["49", "50", "51", "52", "53", "55", "56", "58", "59", "60", "61", "62", "63", "64", "65", "66", "68", "69", "70", "71", "72", "73", "74", "75", "77", "78", "79", "80", "81", "82", "85", "86", "87", "88", "90", "91", "92", "93", "94", "95", "96"],
    "Administration publique": ["84"],
}
ALL_NAF = sorted({code for values in NAF_GROUPS.values() for code in values})


def _selected_groups(allowed: list[str]) -> list[str]:
    allowed_set = {str(value).zfill(2) for value in allowed}
    return [label for label, codes in NAF_GROUPS.items() if set(codes).issubset(allowed_set)]


def render_targeting(config: dict, sha: str) -> None:
    edited = deepcopy(config)
    st.subheader("Ciblage")
    st.caption("Ces paramètres définissent ce que MARKETIA recherche. Les filtres du Dashboard et du Radar ne modifient que l'affichage.")

    st.markdown("## 1. Entreprises recherchées")
    q = edited.setdefault("qualification", {})
    target = edited.setdefault("target", {})
    a, b, c = st.columns([2, 1, 1])
    with a:
        target["headquarters_country"] = st.multiselect("Pays de siège ciblés", COUNTRIES, default=target.get("headquarters_country", ["FR"]), key="target_countries")
    with b:
        q["min_employees"] = int(st.number_input("Effectif minimum", min_value=1, max_value=100000, value=int(q.get("min_employees", 40)), step=10, key="target_min_employees"))
    with c:
        q["require_company_metadata"] = st.toggle("Métadonnées obligatoires", value=bool(q.get("require_company_metadata", True)), key="target_metadata")
    q["enabled"] = True

    current_allowed = [str(x).zfill(2) for x in q.get("allowed_naf_divisions", [])]
    groups = st.multiselect("Activités ciblées", list(NAF_GROUPS), default=_selected_groups(current_allowed), key="target_activity_groups")
    if groups:
        q["allowed_naf_divisions"] = sorted({code for group in groups for code in NAF_GROUPS[group]})
    with st.expander("Réglages avancés des activités (codes NAF)"):
        q["allowed_naf_divisions"] = st.multiselect("Divisions NAF autorisées", ALL_NAF, default=[str(x).zfill(2) for x in q.get("allowed_naf_divisions", [])], key="target_naf")

    st.divider(); st.markdown("## 2. Besoins recherchés")
    st.caption("Active les familles de besoins et ajuste leur importance relative.")
    for market_id, market in edited.get("markets", {}).items():
        x, y, z = st.columns([4, 1, 2])
        with x:
            market["enabled"] = st.checkbox(market.get("label", market_id), value=bool(market.get("enabled", True)), key=f"market_enabled_{market_id}")
        with y:
            market["weight"] = int(st.number_input("Importance", 0, 100, int(market.get("weight", 10)), key=f"market_weight_{market_id}"))
        with z:
            st.caption(", ".join(market.get("keywords", [])[:4]))

    st.divider(); st.markdown("## 3. Signaux surveillés")
    jobs = edited.setdefault("job_signals", {})
    web = edited.setdefault("web_signals", {})
    automation = edited.setdefault("automation", {})
    a, b, c = st.columns(3)
    with a: jobs["enabled"] = st.toggle("Recrutements IT", value=bool(jobs.get("enabled", True)), key="signal_jobs")
    with b: web["enabled"] = st.toggle("Expansion / actualités", value=bool(web.get("enabled", True)), key="signal_web")
    with c: automation["lookback_days"] = int(st.number_input("Période analysée (jours)", 1, 90, int(automation.get("lookback_days", 14)), key="signal_lookback"))

    with st.expander("Sources et secteurs thématiques"):
        st.markdown("#### Sources")
        for source_id, source in edited.get("sources", {}).items():
            source["enabled"] = st.checkbox(source_id.upper(), value=bool(source.get("enabled", True)), key=f"source_{source_id}")
        st.markdown("#### Secteurs thématiques")
        for sector in edited.get("sectors", []):
            x, y = st.columns([4, 1])
            with x: sector["enabled"] = st.checkbox(sector.get("label", sector.get("id", "Secteur")), value=bool(sector.get("enabled", True)), key=f"sector_{sector['id']}")
            with y: sector["weight"] = int(st.number_input("Importance", 0, 100, int(sector.get("weight", 10)), key=f"sector_weight_{sector['id']}"))

    st.divider(); st.markdown("## 4. Priorisation")
    scoring = edited.setdefault("scoring", {})
    alerts = edited.setdefault("alerts", {})
    a, b, c = st.columns(3)
    with a: scoring["infra_fit_weight"] = st.slider("Adéquation infrastructure", 0.0, 1.0, float(scoring.get("infra_fit_weight", 0.35)), 0.05, key="score_infra")
    with b: scoring["buying_intent_weight"] = st.slider("Intention d'achat", 0.0, 1.0, float(scoring.get("buying_intent_weight", 0.45)), 0.05, key="score_buying")
    with c: scoring["timing_weight"] = st.slider("Timing", 0.0, 1.0, float(scoring.get("timing_weight", 0.20)), 0.05, key="score_timing")
    total = scoring["infra_fit_weight"] + scoring["buying_intent_weight"] + scoring["timing_weight"]
    if abs(total - 1.0) > 0.001:
        st.warning(f"La somme des pondérations vaut {total:.2f}. Recommandé : 1.00")
    a, b, c = st.columns(3)
    with a: alerts["minimum_score"] = int(st.number_input("Seuil WARM / alerte", 0, 100, int(alerts.get("minimum_score", 65)), key="threshold_warm"))
    with b: alerts["hot_score"] = int(st.number_input("Seuil HOT", 0, 100, int(alerts.get("hot_score", 80)), key="threshold_hot"))
    with c: alerts["critical_score"] = int(st.number_input("Seuil CRITICAL", 0, 100, int(alerts.get("critical_score", 90)), key="threshold_critical"))

    with st.expander("Configuration avancée"):
        st.code(yaml.safe_dump(edited, sort_keys=False, allow_unicode=True), language="yaml")

    st.divider()
    left, right = st.columns([1.5, 4])
    with left: save = st.button("Enregistrer & relancer MARKETIA", type="primary", use_container_width=True)
    with right: st.caption("Enregistre config.yaml puis déclenche automatiquement un nouveau calcul MARKETIA.")
    if save:
        try:
            commit_sha = save_config(edited, sha)
            load_config.clear(); load_workflow_runs.clear()
            st.success(f"Ciblage enregistré. Commit : {commit_sha[:8]}")
            st.info("MARKETIA recalcule maintenant les résultats avec ce nouveau périmètre.")
        except Exception as exc:
            st.error(f"Échec de l'enregistrement : {exc}")
