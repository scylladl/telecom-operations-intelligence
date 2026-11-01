"""NorthGrid Network Operations: Streamlit version of the Power BI report, on the same rpt views.

    streamlit run streamlit_app.py
"""
import os
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from dotenv import load_dotenv

APP = Path(__file__).parent
load_dotenv(APP / ".env")

import ui  # noqa: E402  (db reads the connection settings loaded above)

st.set_page_config(page_title="NorthGrid Network Operations", page_icon=":material/cell_tower:", layout="wide")

AUTH_FILE = APP / "auth.yaml"
if not AUTH_FILE.exists():
    st.error("No users yet. Create one with `python manage_users.py <username> --name \"First Last\" "
             "--email <email>` (app/README.md).")
    st.stop()

# Credentials only: the cookie key stays in .env, not next to the password hashes.
credentials = yaml.safe_load(AUTH_FILE.read_text(encoding="utf-8"))["credentials"]
authenticator = stauth.Authenticate(credentials, cookie_name="northgrid_ops_auth",
                                    cookie_key=os.environ["AUTH_COOKIE_KEY"], cookie_expiry_days=1,
                                    auto_hash=False)
authenticator.login(location="main", fields={"Form name": "NorthGrid Network Operations"})

if not st.session_state.get("authentication_status"):
    if st.session_state.get("authentication_status") is False:
        st.error("Incorrect username or password.")
    st.caption("Simulated scenario: NorthGrid Telecom and its data are fictional.")
    st.stop()

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
st.session_state["filters"] = ui.sidebar_filters(data)
with st.sidebar:
    st.divider()
    st.caption(f"Signed in as {st.session_state['name']}")
    authenticator.logout("Sign out", location="sidebar")

pages.run()
