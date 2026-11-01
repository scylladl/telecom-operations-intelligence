"""Add a dashboard user, or reset their password, in auth.yaml (bcrypt hash; the file is not committed).

    python manage_users.py <username> --name "First Last" --email user@example.com
"""
import argparse
import getpass
import sys
from pathlib import Path

import yaml
from streamlit_authenticator.utilities.hasher import Hasher

AUTH_FILE = Path(__file__).with_name("auth.yaml")


def save_user(username: str, name: str, email: str, password: str) -> str:
    config = yaml.safe_load(AUTH_FILE.read_text(encoding="utf-8")) if AUTH_FILE.exists() else None
    config = config or {"credentials": {"usernames": {}}}
    first_name, _, last_name = name.partition(" ")
    username = username.lower()  # the authenticator compares usernames in lower case
    config["credentials"]["usernames"][username] = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "password": Hasher.hash(password),
    }
    AUTH_FILE.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return username


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    if len(password) < 12:
        sys.exit("Use at least 12 characters.")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match.")
    print(f"Saved user '{save_user(args.username, args.name, args.email, password)}' in {AUTH_FILE.name}.")


if __name__ == "__main__":
    main()
