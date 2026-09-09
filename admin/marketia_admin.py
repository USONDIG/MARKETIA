from __future__ import annotations

import base64
import hmac
from copy import deepcopy

import pandas as pd
import requests
import streamlit as st
import yaml

REPO = "USONDIG/MARKETIA"
CONFIG_PATH = "config.yaml"
WORKFLOW_FILE = "radar.yml"
GITHUB_API = f"https://api.github.com/repos/{REPO}/contents/{CONFIG_PATH}"
ACTIONS_API = f"https://api.github.com/repos/{REPO}/actions"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/output/grafana"

NAF_GROUPS = {
    "Agriculture": [f"{n:02d}" for n in range(1, 4)],
    "Industrie": [f"{n:02d}" for n in range(5, 40)],
    "Construction": ["41", "42", "43"],
    "Commerce": ["45", "46", "47"],
    "Services": [
        "49", "50", "51", "52", "53", "55", "56", "58", "59", "60", "61", "62", "63",
        "64", "65", "66", "68", "69", "70", "71", "72", "73", "74", "75", "77", "78", "79",
        "80", "81", "82", "85", "86", "87", "88", "90", "91", "92", "93", "94", "95", "96",
    ],
    "Administration publique": ["84"],
}
ALL_NAF = sorted({code for values in NAF_GROUPS.values() for code in values})


def _headers() -> dict[str, str]:
    token = st.secrets.get("github_token", "")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _authenticated() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.title("MARKETIA — Administration")
    st.caption("Connexion requise")
    with st.form("login"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", use_container_width=True)
    if submitted:
        expected_user = str(st.secrets.get("admin_username", ""))
        expected_password = str(st.secrets.get("admin_password", ""))
        if hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_password):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Identifiant ou mot de passe incorrect.")
    return False


@st.cache_data(ttl=30, show_spinner=False)
def load_config() -> tuple[dict, str]:
    response = requests.get(GITHUB_API, headers=_headers(), timeout=20)
    response.raise_for_status()
    payload = response.json()
    raw = base64.b64decode(payload["content"]).decode("utf-8")
    return yaml.safe_load(raw), payload["sha"]


@st.cache_data(ttl=60, show_spinner=False)
def load_json_feed(name: str):
    response = requests.get(f"{RAW_BASE}/{name}", timeout=20)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=20, show_spinner=False)
def load_workflow_runs(limit: int = 5) -> list[dict]:
    response = requests.get(
        f"{ACTIONS_API}/workflows/{WORKFLOW_FILE}/runs",
        headers=_headers(),
        params={"branch": "main", "per_page": limit},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("workflow_runs", [])


def trigger_workflow() -> None:
    response = requests.post(
        f"{ACTIONS_API}/workflows/{WORKFLOW_FILE}/dispatches",
        headers=_headers(), json={"ref": "main"}, timeout=20,
    )
    response.raise_for_status()


def rerun_workflow(run_id: int) -> None:
    response = requests.post(f"{ACTIONS_API}/runs/{run_id}/rerun", headers=_headers(), timeout=20)
    response.raise_for_status()


def save_config(config: dict, sha: str) -> str:
    encoded = base64.b64encode(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True).encode("utf-8")
    ).decode("ascii")
    payload = {
        "message": "chore: update MARKETIA targeting from admin console",
        "content": encoded,
        "sha": sha,
        "branch": "main",
    }
    response = requests.put(GITHUB_API, headers=_headers(), json=payload, timeout=30)
    response.raise_for_status()
    return response.json()["commit"]["sha"]


def _selected_groups(allowed: list[str]) -> list[str]:
    selected = []
    allowed_set = set(allowed)
    for label, codes in NAF_GROUPS.items():
        if set(codes).issubset(allowed_set):
            selected.append(label)
    return selected


def _safe_df(payload) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame()
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        return pd.DataFrame([payload])
    return pd.DataFrame()


def _run_state(run: dict) -> tuple[str, str]:
    status = str(run.get("status") or "unknown")
    conclusion = str(run.get("conclusion") or "")
    if status == "queued":
        return "🟡", "En attente"
    if status in {"in_progress", "requested", "waiting", "pending"}:
        return "🔵", "En cours"
    if conclusion == "success":
        return "🟢", "Réussi"
    if conclusion in {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}:
        return "🔴", "Échoué"
    if status == "completed":
        return "⚪", conclusion or "Terminé"
    return "⚪", status


def render_run_status() -> None:
    st.markdown("### État des runs MARKETIA")
    try:
        runs = load_workflow_runs(5)
    except Exception as exc:
        st.error(f"Impossible de lire les runs GitHub Actions : {exc}")
        return
    if not runs:
        st.info("Aucun run MARKETIA trouvé.")
        return

    latest = runs[0]
    icon, label = _run_state(latest)
    created = str(latest.get("created_at") or "").replace("T", " ").replace("Z", " UTC")
    c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
    c1.metric("Dernier run", f"#{latest.get('run_number', '?')}")
    c2.metric("État", f"{icon} {label}")
    c3.metric("Déclenchement", latest.get("event", "—"))
    c4.metric("Date", created or "—")

    a, b, _ = st.columns([1, 1, 3])
    with a:
        if st.button("Actualiser", key="refresh_runs", use_container_width=True):
            load_workflow_runs.clear()
            load_json_feed.clear()
            st.rerun()
    with b:
        if st.button("Lancer maintenant", key="trigger_run", type="primary", use_container_width=True):
            try:
                trigger_workflow()
                load_workflow_runs.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Impossible de lancer MARKETIA : {exc}")

    rows = []
    for run in runs:
        run_icon, run_label = _run_state(run)
        rows.append({
            "Run": f"#{run.get('run_number', '?')}",
            "État": f"{run_icon} {run_label}",
            "Déclencheur": run.get("event", ""),
            "Titre": run.get("display_title", ""),
            "Créé": str(run.get("created_at") or "").replace("T", " ").replace("Z", " UTC"),
            "URL": run.get("html_url", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    rerunnable = [run for run in runs if run.get("status") == "completed"]
    if rerunnable:
        choices = {
            f"#{run.get('run_number')} — {_run_state(run)[1]} — {run.get('display_title', 'MARKETIA Radar')}": run
            for run in rerunnable
        }
        selected_label = st.selectbox("Run à relancer", list(choices), key="rerun_selector")
        selected_run = choices[selected_label]
        if st.button("Relancer le run sélectionné", key="rerun_selected"):
            try:
                rerun_workflow(int(selected_run["id"]))
                load_workflow_runs.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Impossible de relancer ce run : {exc}")
    st.divider()


def render_dashboard() -> None:
    st.subheader("Dashboard MARKETIA")
    st.caption("Vue des opportunités qualifiées.")
    render_run_status()
    try:
        stats = _safe_df(load_json_feed("dashboard_stats.json"))
        opportunities = _safe_df(load_json_feed("opportunities.json"))
        signals = _safe_df(load_json_feed("signals.json"))
        events = _safe_df(load_json_feed("events.json"))
        market_summary = _safe_df(load_json_feed("market_summary.json"))
        country_summary = _safe_df(load_json_feed("country_summary.json"))
        source_summary = _safe_df(load_json_feed("source_summary.json"))
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
        c5.metric("Score moyen", float(row.get("avg_score", 0) or 0))

    with st.expander("Filtres", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        priorities = sorted(opportunities.get("priority", pd.Series(dtype=str)).dropna().unique().tolist()) if not opportunities.empty else []
        countries = sorted(opportunities.get("country", pd.Series(dtype=str)).dropna().unique().tolist()) if not opportunities.empty else []
        with f1:
            selected_priorities = st.multiselect("Priorité", priorities, default=priorities, key="opp_priorities")
        with f2:
            selected_countries = st.multiselect("Pays", countries, default=countries, key="opp_countries")
        with f3:
            min_score = st.slider("Score minimum", 0, 100, 0, key="opp_score")
        with f4:
            company_search = st.text_input("Entreprise contient", "", key="opp_search")

    filtered = opportunities.copy()
    if not filtered.empty:
        if selected_priorities:
            filtered = filtered[filtered["priority"].isin(selected_priorities)]
        if selected_countries and "country" in filtered.columns:
            filtered = filtered[filtered["country"].isin(selected_countries)]
        if "opportunity_score" in filtered.columns:
            filtered = filtered[pd.to_numeric(filtered["opportunity_score"], errors="coerce").fillna(0) >= min_score]
        if company_search and "company_name" in filtered.columns:
            filtered = filtered[filtered["company_name"].astype(str).str.contains(company_search, case=False, na=False)]

    left, right = st.columns([2, 1])
    with left:
        st.markdown("### Top opportunités")
        preferred = ["priority", "opportunity_score", "company_name", "country", "naf", "employees", "infra_fit", "buying_intent", "timing", "top_signal"]
        cols = [c for c in preferred if c in filtered.columns]
        st.dataframe(filtered[cols] if cols else filtered, use_container_width=True, hide_index=True, height=420)
    with right:
        st.markdown("### Répartition par pays")
        if not country_summary.empty and {"country", "opportunities"}.issubset(country_summary.columns):
            st.bar_chart(country_summary[["country", "opportunities"]].dropna().set_index("country"))
        else:
            st.info("Pas encore de données pays.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Signaux par marché")
        if not market_summary.empty and {"label", "count"}.issubset(market_summary.columns):
            st.bar_chart(market_summary[["label", "count"]].set_index("label"))
        else:
            st.info("Pas encore de synthèse marché.")
    with c2:
        st.markdown("### Événements par source")
        if not source_summary.empty and {"source", "count"}.issubset(source_summary.columns):
            st.bar_chart(source_summary[["source", "count"]].set_index("source"))
        else:
            st.info("Pas encore de synthèse source.")

    st.markdown("### Pourquoi maintenant ?")
    companies = sorted(filtered["company_name"].dropna().astype(str).unique().tolist()) if not filtered.empty and "company_name" in filtered.columns else []
    selected_company = st.selectbox("Choisir une entreprise", [""] + companies, key="opp_company")
    if selected_company:
        company_signals = signals[signals["company_name"].astype(str) == selected_company] if not signals.empty and "company_name" in signals.columns else pd.DataFrame()
        company_events = events[events["company_name"].astype(str) == selected_company] if not events.empty and "company_name" in events.columns else pd.DataFrame()
        s1, s2 = st.columns(2)
        with s1:
            cols = [c for c in ["event_date", "source", "signal_type", "label", "strength", "title", "url"] if c in company_signals.columns]
            st.dataframe(company_signals[cols] if cols else company_signals, use_container_width=True, hide_index=True, height=320)
        with s2:
            cols = [c for c in ["event_date", "source", "event_type", "title", "detected_signals", "url"] if c in company_events.columns]
            st.dataframe(company_events[cols] if cols else company_events, use_container_width=True, hide_index=True, height=320)

    grafana_url = str(st.secrets.get("grafana_url", "")).strip()
    if grafana_url:
        st.link_button("Ouvrir Grafana pour l'analyse avancée", grafana_url)


def render_discovery() -> None:
    st.subheader("📡 Radar / Discovery")
    st.caption("Vue large des comptes détectés, même lorsqu'ils ne sont pas encore totalement enrichis ou qualifiés.")
    try:
        discovery = _safe_df(load_json_feed("discovery.json"))
        stats = _safe_df(load_json_feed("dashboard_stats.json"))
    except Exception as exc:
        st.error(f"Impossible de charger le Radar Discovery : {exc}")
        return

    if st.button("Actualiser Discovery", key="refresh_discovery"):
        load_json_feed.clear()
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
        [value for value in discovery.get("employee_range", pd.Series(dtype=str)).dropna().astype(str).unique().tolist() if value != "Inconnu"]
    )

    with st.expander("Filtres Discovery", expanded=True):
        a, b, c, d = st.columns(4)
        priorities = sorted(discovery.get("discovery_priority", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        statuses = sorted(discovery.get("status", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        countries = sorted(discovery.get("country", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        with a:
            selected_priorities = st.multiselect("Priorité Discovery", priorities, default=priorities, key="disc_priorities")
        with b:
            selected_statuses = st.multiselect("Statut", statuses, default=statuses, key="disc_statuses")
        with c:
            selected_countries = st.multiselect("Pays", countries, default=countries, key="disc_countries")
        with d:
            min_score = st.slider("Score Discovery minimum", 0, 100, 0, key="disc_score")

        e, f, g = st.columns([2, 2, 3])
        with e:
            selected_employee_ranges = st.multiselect(
                "Tranches d'effectif",
                employee_ranges,
                default=employee_ranges,
                key="disc_employee_ranges",
                help="Les comptes avec effectif inconnu restent visibles sauf si un effectif minimum est demandé.",
            )
        with f:
            min_employees = int(st.number_input(
                "Effectif minimum connu",
                min_value=0,
                max_value=100000,
                value=0,
                step=10,
                key="disc_min_employees",
            ))
        with g:
            search = st.text_input("Entreprise / signal / marché contient", "", key="disc_search")

    filtered = discovery.copy()
    if selected_priorities and "discovery_priority" in filtered.columns:
        filtered = filtered[filtered["discovery_priority"].isin(selected_priorities)]
    if selected_statuses and "status" in filtered.columns:
        filtered = filtered[filtered["status"].isin(selected_statuses)]
    if selected_countries and "country" in filtered.columns:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if "discovery_score" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["discovery_score"], errors="coerce").fillna(0) >= min_score]

    if "employee_range" in filtered.columns and selected_employee_ranges:
        known_mask = filtered["employee_range"].isin(selected_employee_ranges)
        unknown_mask = filtered["employee_range"].fillna("Inconnu").eq("Inconnu")
        filtered = filtered[known_mask | unknown_mask]

    if min_employees > 0 and "employee_min" in filtered.columns:
        employee_min = pd.to_numeric(filtered["employee_min"], errors="coerce")
        filtered = filtered[employee_min >= min_employees]

    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ["company_name", "markets", "top_signals", "sources"]:
            if column in filtered.columns:
                mask |= filtered[column].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    st.markdown(f"### Comptes détectés — {len(filtered)}")
    preferred = [
        "discovery_priority", "discovery_score", "status", "company_name", "country", "country_code", "naf",
        "employee_range", "employee_min", "event_count", "signal_count", "sources", "markets", "top_signals",
        "latest_event_date", "latest_title", "latest_url",
    ]
    cols = [c for c in preferred if c in filtered.columns]
    st.dataframe(filtered[cols] if cols else filtered, use_container_width=True, hide_index=True, height=650)
    st.info("DISCOVERED = signal détecté ; IDENTIFIED = entreprise identifiée ; ENRICHED = métadonnées disponibles ; QUALIFIED = conforme au ciblage MARKETIA.")


def main() -> None:
    st.set_page_config(page_title="MARKETIA Admin", page_icon="🎯", layout="wide")
    if not _authenticated():
        st.stop()

    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.title("MARKETIA — Console de ciblage")
        st.caption("Dashboard commercial et configuration MARKETIA dans une seule interface.")
    with top_right:
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if not st.secrets.get("github_token"):
        st.error("Secret `github_token` absent. Configure les Secrets Streamlit avant utilisation.")
        st.stop()

    try:
        config, sha = load_config()
    except Exception as exc:
        st.error(f"Impossible de lire config.yaml depuis GitHub : {exc}")
        st.stop()

    edited = deepcopy(config)

    tab_dashboard, tab_discovery, tab_target, tab_sectors, tab_markets, tab_scoring, tab_raw = st.tabs(
        ["Dashboard", "📡 Radar / Discovery", "Ciblage", "Secteurs", "Marchés", "Scoring", "Avancé"]
    )

    with tab_dashboard:
        render_dashboard()
    with tab_discovery:
        render_discovery()
    with tab_target:
        q = edited.setdefault("qualification", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            q["enabled"] = st.toggle("Activer la qualification", value=bool(q.get("enabled", True)))
        with c2:
            q["require_company_metadata"] = st.toggle("Métadonnées entreprise obligatoires", value=bool(q.get("require_company_metadata", True)))
        with c3:
            q["min_employees"] = int(st.number_input("Effectif minimum", min_value=1, max_value=100000, value=int(q.get("min_employees", 50)), step=10))

        current_allowed = [str(x).zfill(2) for x in q.get("allowed_naf_divisions", [])]
        groups = st.multiselect("Familles d'activité autorisées", options=list(NAF_GROUPS), default=_selected_groups(current_allowed))
        default_from_groups = sorted({code for group in groups for code in NAF_GROUPS[group]})
        q["allowed_naf_divisions"] = st.multiselect("Divisions NAF autorisées", options=ALL_NAF, default=default_from_groups if groups else current_allowed)

        target = edited.setdefault("target", {})
        target["headquarters_country"] = st.multiselect(
            "Pays de siège ciblés",
            options=["FR", "BE", "DE", "NL", "ES", "IT", "LU", "AT", "PT", "IE", "DK", "SE", "FI", "PL", "CZ"],
            default=target.get("headquarters_country", ["FR"]),
        )

    with tab_sectors:
        st.caption("Active/désactive les secteurs et ajuste leur poids.")
        for sector in edited.get("sectors", []):
            cols = st.columns([4, 1, 2])
            with cols[0]:
                sector["enabled"] = st.checkbox(sector.get("label", sector.get("id", "Secteur")), value=bool(sector.get("enabled", True)), key=f"sector_enabled_{sector['id']}")
            with cols[1]:
                sector["weight"] = int(st.number_input("Poids", min_value=0, max_value=100, value=int(sector.get("weight", 10)), key=f"sector_weight_{sector['id']}"))
            with cols[2]:
                st.caption(", ".join(sector.get("keywords", [])[:5]))

    with tab_markets:
        st.caption("Active/désactive les marchés infrastructure et ajuste leur poids.")
        for market_id, market in edited.get("markets", {}).items():
            cols = st.columns([4, 1, 2])
            with cols[0]:
                market["enabled"] = st.checkbox(market.get("label", market_id), value=bool(market.get("enabled", True)), key=f"market_enabled_{market_id}")
            with cols[1]:
                market["weight"] = int(st.number_input("Poids", min_value=0, max_value=100, value=int(market.get("weight", 10)), key=f"market_weight_{market_id}"))
            with cols[2]:
                st.caption(", ".join(market.get("keywords", [])[:5]))

    with tab_scoring:
        alerts = edited.setdefault("alerts", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            alerts["minimum_score"] = int(st.number_input("Seuil WARM / alerte", 0, 100, int(alerts.get("minimum_score", 65))))
        with c2:
            alerts["hot_score"] = int(st.number_input("Seuil HOT", 0, 100, int(alerts.get("hot_score", 80))))
        with c3:
            alerts["critical_score"] = int(st.number_input("Seuil CRITICAL", 0, 100, int(alerts.get("critical_score", 90))))

        scoring = edited.setdefault("scoring", {})
        st.subheader("Pondération du score")
        c1, c2, c3 = st.columns(3)
        with c1:
            scoring["infra_fit_weight"] = st.slider("Infra fit", 0.0, 1.0, float(scoring.get("infra_fit_weight", 0.35)), 0.05)
        with c2:
            scoring["buying_intent_weight"] = st.slider("Buying intent", 0.0, 1.0, float(scoring.get("buying_intent_weight", 0.45)), 0.05)
        with c3:
            scoring["timing_weight"] = st.slider("Timing", 0.0, 1.0, float(scoring.get("timing_weight", 0.20)), 0.05)
        total = scoring["infra_fit_weight"] + scoring["buying_intent_weight"] + scoring["timing_weight"]
        if abs(total - 1.0) > 0.001:
            st.warning(f"La somme des pondérations vaut {total:.2f}. Recommandé : 1.00")

    with tab_raw:
        st.caption("Vue YAML générée. Lecture seule pour éviter les erreurs de syntaxe.")
        st.code(yaml.safe_dump(edited, sort_keys=False, allow_unicode=True), language="yaml")

    st.divider()
    c1, c2 = st.columns([1, 4])
    with c1:
        save = st.button("Enregistrer", type="primary", use_container_width=True)
    with c2:
        st.caption("Un commit sur config.yaml déclenchera automatiquement le workflow MARKETIA Radar.")

    if save:
        try:
            commit_sha = save_config(edited, sha)
            load_config.clear()
            st.success(f"Configuration enregistrée. Commit : {commit_sha[:8]}")
            st.info("MARKETIA va recalculer automatiquement les résultats via GitHub Actions.")
        except requests.HTTPError as exc:
            st.error(f"Échec de l'enregistrement GitHub : {exc.response.text[:500]}")
        except Exception as exc:
            st.error(f"Échec de l'enregistrement : {exc}")


if __name__ == "__main__":
    main()
