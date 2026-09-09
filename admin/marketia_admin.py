from __future__ import annotations

import base64
import hmac
from copy import deepcopy

import requests
import streamlit as st
import yaml

REPO = "USONDIG/MARKETIA"
CONFIG_PATH = "config.yaml"
GITHUB_API = f"https://api.github.com/repos/{REPO}/contents/{CONFIG_PATH}"

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
        user_ok = hmac.compare_digest(username, expected_user)
        pass_ok = hmac.compare_digest(password, expected_password)
        if user_ok and pass_ok:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Identifiant ou mot de passe incorrect.")
    return False


@st.cache_data(ttl=30, show_spinner=False)
def load_config() -> tuple[dict, str]:
    response = requests.get(GITHUB_API, headers=_headers(), timeout=20)
    response.raise_for_status()
    payload = response.json()
    raw = base64.b64decode(payload["content"]).decode("utf-8")
    return yaml.safe_load(raw), payload["sha"]


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


def main() -> None:
    st.set_page_config(page_title="MARKETIA Admin", page_icon="🎯", layout="wide")
    if not _authenticated():
        st.stop()

    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.title("MARKETIA — Console de ciblage")
        st.caption("Les modifications sont enregistrées dans config.yaml et déclenchent automatiquement MARKETIA.")
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

    tab_target, tab_sectors, tab_markets, tab_scoring, tab_raw = st.tabs(
        ["Ciblage", "Secteurs", "Marchés", "Scoring", "Avancé"]
    )

    with tab_target:
        q = edited.setdefault("qualification", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            q["enabled"] = st.toggle("Activer la qualification", value=bool(q.get("enabled", True)))
        with c2:
            q["require_company_metadata"] = st.toggle(
                "Métadonnées entreprise obligatoires", value=bool(q.get("require_company_metadata", True))
            )
        with c3:
            q["min_employees"] = int(
                st.number_input("Effectif minimum", min_value=1, max_value=100000, value=int(q.get("min_employees", 50)), step=10)
            )

        current_allowed = [str(x).zfill(2) for x in q.get("allowed_naf_divisions", [])]
        groups = st.multiselect(
            "Familles d'activité autorisées",
            options=list(NAF_GROUPS),
            default=_selected_groups(current_allowed),
            help="Sélectionne les grandes familles. Tu peux affiner les divisions NAF juste en dessous.",
        )
        default_from_groups = sorted({code for group in groups for code in NAF_GROUPS[group]})
        q["allowed_naf_divisions"] = st.multiselect(
            "Divisions NAF autorisées",
            options=ALL_NAF,
            default=default_from_groups if groups else current_allowed,
        )

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
