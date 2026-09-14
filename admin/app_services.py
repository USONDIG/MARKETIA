from __future__ import annotations

import base64
import hmac

import requests
import streamlit as st
import yaml

REPO = "USONDIG/MARKETIA"
CONFIG_PATH = "config.yaml"
WORKFLOW_FILE = "radar.yml"
GITHUB_API = f"https://api.github.com/repos/{REPO}/contents/{CONFIG_PATH}"
ACTIONS_API = f"https://api.github.com/repos/{REPO}/actions"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/output/grafana"


def headers() -> dict[str, str]:
    token = st.secrets.get("github_token", "")
    return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}


def authenticated() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.title("MARKETIA")
    st.caption("Connexion à la console commerciale")
    with st.form("login"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", use_container_width=True)
    if submitted:
        if hmac.compare_digest(username, str(st.secrets.get("admin_username", ""))) and hmac.compare_digest(password, str(st.secrets.get("admin_password", ""))):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Identifiant ou mot de passe incorrect.")
    return False


@st.cache_data(ttl=30, show_spinner=False)
def load_config() -> tuple[dict, str]:
    response = requests.get(GITHUB_API, headers=headers(), timeout=20)
    response.raise_for_status()
    payload = response.json()
    return yaml.safe_load(base64.b64decode(payload["content"]).decode("utf-8")), payload["sha"]


@st.cache_data(ttl=60, show_spinner=False)
def load_json_feed(name: str):
    response = requests.get(f"{RAW_BASE}/{name}", timeout=20)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=20, show_spinner=False)
def load_workflow_runs(limit: int = 5) -> list[dict]:
    response = requests.get(f"{ACTIONS_API}/workflows/{WORKFLOW_FILE}/runs", headers=headers(), params={"branch": "main", "per_page": limit}, timeout=20)
    response.raise_for_status()
    return response.json().get("workflow_runs", [])


def trigger_workflow() -> None:
    response = requests.post(f"{ACTIONS_API}/workflows/{WORKFLOW_FILE}/dispatches", headers=headers(), json={"ref": "main"}, timeout=20)
    response.raise_for_status()


def save_config(config: dict, sha: str) -> str:
    encoded = base64.b64encode(yaml.safe_dump(config, sort_keys=False, allow_unicode=True).encode("utf-8")).decode("ascii")
    response = requests.put(GITHUB_API, headers=headers(), json={"message": "chore: update MARKETIA targeting from admin console", "content": encoded, "sha": sha, "branch": "main"}, timeout=30)
    response.raise_for_status()
    return response.json()["commit"]["sha"]


def run_state(run: dict) -> tuple[str, str]:
    status = str(run.get("status") or "unknown")
    conclusion = str(run.get("conclusion") or "")
    if status == "queued": return "🟡", "En attente"
    if status in {"in_progress", "requested", "waiting", "pending"}: return "🔵", "En cours"
    if conclusion == "success": return "🟢", "Réussi"
    if conclusion in {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}: return "🔴", "Échoué"
    return "⚪", conclusion or status


def render_run_status(compact: bool = False) -> None:
    try:
        runs = load_workflow_runs(5)
    except Exception as exc:
        st.error(f"Impossible de lire les runs GitHub Actions : {exc}")
        return
    if not runs: return
    latest = runs[0]
    icon, label = run_state(latest)
    created = str(latest.get("created_at") or "").replace("T", " ").replace("Z", " UTC")
    if compact:
        st.caption(f"Dernier run #{latest.get('run_number', '?')} · {icon} {label} · {created}")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Run", f"#{latest.get('run_number', '?')}")
    c2.metric("État", f"{icon} {label}")
    c3.metric("Date", created or "—")


def render_top_bar() -> None:
    try: runs = load_workflow_runs(1)
    except Exception: runs = []
    latest = runs[0] if runs else {}
    icon, label = run_state(latest) if latest else ("⚪", "Inconnu")
    created = str(latest.get("created_at") or "").replace("T", " ").replace("Z", " UTC")
    title, status, refresh, launch, logout = st.columns([4, 2, 1, 1.2, 1])
    with title:
        st.title("MARKETIA")
        st.caption("Intelligence commerciale infrastructure — du signal à l'action")
    with status:
        st.write(""); st.write(f"**{icon} {label}**"); st.caption(f"Run #{latest.get('run_number', '—')} · {created[:16] if created else '—'}")
    with refresh:
        st.write("")
        if st.button("Actualiser", use_container_width=True):
            load_workflow_runs.clear(); load_json_feed.clear(); st.rerun()
    with launch:
        st.write("")
        if st.button("Lancer MARKETIA", type="primary", use_container_width=True):
            try: trigger_workflow(); load_workflow_runs.clear(); st.rerun()
            except Exception as exc: st.error(f"Impossible de lancer MARKETIA : {exc}")
    with logout:
        st.write("")
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.clear(); st.rerun()
