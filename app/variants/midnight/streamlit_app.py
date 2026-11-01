"""NorthGrid Network Operations, Midnight Ops design (dark operations room).

    cd app/variants/midnight
    streamlit run streamlit_app.py
"""
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

HERE = Path(__file__).parent
APP = HERE.parents[1]
sys.path.insert(0, str(APP))  # shared modules: auth, db, kpis, narrative, ui
load_dotenv(APP / ".env")

import auth  # noqa: E402
import pages  # noqa: E402
import ui  # noqa: E402

ui.set_theme(pages.THEME)
st.set_page_config(page_title="NorthGrid · Midnight Ops", page_icon=":material/monitoring:", layout="wide")
st.html(HERE / "style.css")
st.logo(HERE / "logo.svg", size="large")
authenticator = auth.require_login()

navigation = st.navigation([
    st.Page(pages.overview, title="Overview", icon=":material/dashboard:", url_path="overview", default=True),
    st.Page(pages.sla, title="SLA and Restoration", icon=":material/timer:", url_path="sla"),
    st.Page(pages.repeat, title="Repeat and Chronic", icon=":material/replay:", url_path="repeat"),
    st.Page(pages.backlog, title="Backlog and Aging", icon=":material/inbox:", url_path="backlog"),
    st.Page(pages.actions, title="Improvement Actions", icon=":material/build:", url_path="actions"),
    st.Page(pages.data_quality, title="Data Quality", icon=":material/fact_check:", url_path="data-quality"),
    st.Page(pages.circuit, title="Circuit Detail", icon=":material/router:", url_path="circuit"),
])

# Filters in one bar above every page, as in an operations room; the sidebar is the navigation rail.
with st.container(key="filterbar"):
    st.session_state["filters"] = ui.filter_controls(ui.load_data(), st.columns([1, 1.4, 1.4, 1.2, 1.2]))

with st.sidebar:
    st.divider()
    st.caption(f"Signed in as {st.session_state['name']}")
    authenticator.logout("Sign out", location="sidebar")

navigation.run()
