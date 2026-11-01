# NorthGrid Network Operations: Streamlit version

> **Simulated scenario.** NorthGrid Telecom, its customers and every value shown are fictional.

A web version of the Power BI report with a login. It reads the same `rpt` views as the Power BI model,
applies the same KPI rules, and has the same seven pages and five filters (month, region, technology, tier,
priority).

## Setup

Requirements: the database built by `build.ps1` (see the main README), Python 3.10 or later, and ODBC Driver 18
for SQL Server. The app connects with Windows authentication, so no database password is stored anywhere.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r app\requirements.txt
cd app
copy .env.example .env      # then set AUTH_COOKIE_KEY (the file explains how)
..\.venv\Scripts\python manage_users.py jdoe --name "Jane Doe" --email jdoe@example.com
..\.venv\Scripts\streamlit run streamlit_app.py
```

`manage_users.py` asks for the password (at least 12 characters) and stores a bcrypt hash in `app/auth.yaml`.
Run it again with the same username to reset a password. `auth.yaml` and `.env` are not committed.

## How it works

| File | Role |
|---|---|
| `db.py` | One SQL query per `rpt` view, with explicit columns |
| `kpis.py` | KPI rules: filters, sums the SQL components and divides (same approach as the DAX measures) |
| `ui.py` | Data cache, sidebar filters, page header, KPI cards, chart styling |
| `streamlit_app.py` | Login (`streamlit-authenticator`), navigation, filters |
| `views/*.py` | One file per page |

- **Same numbers as Power BI by construction.** SQL Server already delivers 1/0 components per ticket and
  daily snapshots (`dw.usp_Refresh`), so the app only filters, sums and divides, exactly like the measures.
  Counts use the opened date, MTTR and SLA the restored date, and backlog, chronic circuits and active circuits
  the last day of the month. The priority filter does not reach chronic circuits, active circuits or
  improvement actions, matching the model relationships.
- **All data is loaded once and cached for 15 minutes.** The views hold about 90,000 rows in total, small enough for pandas
  to filter in memory without a database round trip per filter change, and a new daily processing run shows
  up without a restart.
- **Charts** use one accent colour for the measure and grey for context. Root causes keep a fixed colour each,
  so a filter never repaints the others. Every change on a KPI card shows a sign and an arrow, so colour is never
  the only cue.

## Validation

```powershell
cd app
..\.venv\Scripts\python -m pytest
```

- `tests/test_kpis.py` compares K1, K3, K4, K5, K7 and K9 with `validation/validation_queries.sql`. Those queries
  recompute the KPIs from the source tables without the `dw` layer. The test uses the same three cases and
  tolerances as the Power BI validation: **21 of 21 match**.
- `tests/test_pages.py` renders every page for the latest month and for a filtered slice (January 2024, South,
  P1), the first month with no prior month.
- The pages were also checked in a browser: login with a wrong password and a valid one, every page at 1440 px
  width, the South filter (146 incidents, SLA 65.6%, as in the validation), and circuit NG-FWA-001453
  (22 incidents, MTTR 72.2 h, repeat rate 90.9%).

## Security notes and limitations

- Users and bcrypt hashes are in a local YAML file, and the login cookie is signed with `AUTH_COOKIE_KEY` and
  expires after one day. That suits a single-server deployment. For a company rollout, use the organisation's
  identity provider instead: Streamlit supports OpenID Connect through `st.login`.
- There is no lockout after repeated failed logins.
- All signed-in users see all data. There is no row-level security as in a Power BI role.
- The server listens on `localhost` only (`.streamlit/config.toml`). Exposing it on a network needs HTTPS in
  front of it (reverse proxy) and a read-only SQL login limited to the `rpt` schema.
- `NORTHGRID_SQL_TRUST_SERVER_CERTIFICATE=yes` is only for a local SQL Server with a self-signed certificate.
