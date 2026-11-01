"""NorthGrid Network Operations: Streamlit version of the Power BI report, on the same rpt views.

    streamlit run streamlit_app.py
"""
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

import auth  # noqa: E402  (auth and db read the settings loaded above)
import ui  # noqa: E402

st.set_page_config(page_title="NorthGrid Network Operations", page_icon=":material/cell_tower:", layout="wide")
authenticator = auth.require_login()

pages = st.navigation([
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/sla.py", title="SLA and Restoration", icon=":material/timer:"),
    st.Page("views/repeat.py", title="Repeat and Chronic", icon=":material/replay:"),
    st.Page("views/backlog.py", title="Backlog and Aging", icon=":material/inbox:"),
    st.Page("views/actions.py", title="Improvement Actions", icon=":material/build:"),
    st.Page("views/data_quality.py", title="Data Quality", icon=":material/fact_check:"),
    st.Page("views/circuit.py", title="Circuit Detail", icon=":material/router:"),
])

data = ui.load_data()
st.session_state["filters"] = ui.filter_controls(data)
with st.sidebar:
    st.divider()
    st.caption(f"Signed in as {st.session_state['name']}")
    authenticator.logout("Sign out", location="sidebar")

pages.run()
