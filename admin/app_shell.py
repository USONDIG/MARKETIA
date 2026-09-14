from __future__ import annotations

import streamlit as st

from app_services import authenticated, load_config, load_json_feed, render_run_status, render_top_bar
from dashboard_view import render_qualified_dashboard
from radar_view_v2 import render_radar_discovery
from targeting_view import render_targeting


def main() -> None:
    st.set_page_config(page_title="MARKETIA", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(
        "<style>.block-container{padding-top:1.2rem;padding-bottom:3rem;max-width:1500px}div[data-testid='stMetric']{border:1px solid rgba(120,120,120,.18);border-radius:12px;padding:12px}</style>",
        unsafe_allow_html=True,
    )
    if not authenticated():
        st.stop()
    if not st.secrets.get("github_token"):
        st.error("Secret `github_token` absent. Configure les Secrets Streamlit avant utilisation.")
        st.stop()

    render_top_bar()
    st.divider()

    try:
        config, sha = load_config()
    except Exception as exc:
        st.error(f"Impossible de lire config.yaml depuis GitHub : {exc}")
        st.stop()

    dashboard, radar, targeting = st.tabs(["Dashboard", "Radar / Discovery", "Ciblage"])
    with dashboard:
        render_qualified_dashboard(load_json_feed, render_run_status)
    with radar:
        render_radar_discovery(load_json_feed, key_prefix="main_radar")
    with targeting:
        render_targeting(config, sha)
