"""Login shared by every design: users and bcrypt hashes in auth.yaml, the cookie signing key in .env."""
import os
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml

AUTH_FILE = Path(__file__).with_name("auth.yaml")


def require_login() -> stauth.Authenticate:
    """Show the login form and stop the script until the user is signed in."""
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
    return authenticator
