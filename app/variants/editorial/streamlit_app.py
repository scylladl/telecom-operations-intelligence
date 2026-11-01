"""NorthGrid Network Operations, Editorial design (light narrative report).

    cd app/variants/editorial
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
st.set_page_config(page_title="NorthGrid · Editorial", page_icon=":material/article:", layout="wide",
                   initial_sidebar_state="collapsed")
st.html(HERE / "style.css")
authenticator = auth.require_login()

# Tabs across the top, like the sections of a printed report.
navigation = st.navigation([
    st.Page(pages.overview, title="Overview", url_path="overview", default=True),
    st.Page(pages.sla, title="SLA", url_path="sla"),
    st.Page(pages.repeat, title="Repeat", url_path="repeat"),
    st.Page(pages.backlog, title="Backlog", url_path="backlog"),
    st.Page(pages.actions, title="Actions", url_path="actions"),
    st.Page(pages.data_quality, title="Data quality", url_path="data-quality"),
    st.Page(pages.circuit, title="Circuit", url_path="circuit"),
], position="top")

# The month leads; the other filters wait in a popover so the page reads like an article.
with st.container(key="ed-filters", horizontal=True, vertical_alignment="bottom"):
    month_slot = st.container(width=180)
    more = st.popover("Filters", icon=":material/tune:")
    user = st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="bottom")
st.session_state["filters"] = ui.filter_controls(ui.load_data(), [month_slot, more, more, more, more])
with user:
    st.caption(f"Signed in as {st.session_state['name']}")
    authenticator.logout("Sign out", location="main")

navigation.run()
