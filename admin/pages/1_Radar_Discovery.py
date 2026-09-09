from __future__ import annotations

import requests
import streamlit as st

from admin.radar_view import render_radar_discovery

REPO = "USONDIG/MARKETIA"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/output/grafana"

st.set_page_config(page_title="MARKETIA Radar Discovery", page_icon="📡", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Connecte-toi d'abord depuis la page principale MARKETIA.")
    st.stop()


@st.cache_data(ttl=60, show_spinner=False)
def load_feed(name: str):
    response = requests.get(f"{RAW_BASE}/{name}", timeout=20)
    response.raise_for_status()
    return response.json()


st.title("📡 Radar / Discovery")
render_radar_discovery(load_feed, key_prefix="radar_page")
