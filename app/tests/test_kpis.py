"""The app's KPIs against validation/validation_queries.sql, which recomputes them from the source tables
without the dw layer. Same cases and tolerances as validation/run_validation.ps1 (the Power BI check).
Needs the database built by build.ps1 and app/.env."""
from pathlib import Path

import pandas as pd
import pytest
from dotenv import load_dotenv

APP = Path(__file__).resolve().parents[1]
load_dotenv(APP / ".env")

import db  # noqa: E402  (reads the connection settings loaded above)
import kpis  # noqa: E402

TOLERANCE = {"K1_Incidents": 0, "K3_MttrHours": 0.01, "K4_SlaPct": 1e-6, "K5_RepeatPct": 1e-6,
             "K7_Backlog": 0, "K9_Before": 0, "K9_After": 0}  # dw stores restore hours with 2 decimals


@pytest.fixture(scope="module")
def engine():
    return db.create_engine()


@pytest.fixture(scope="module")
def data(engine):
    return kpis.prepare(db.read_views(engine))


@pytest.fixture(scope="module")
def expected(engine):
    sql = (APP.parent / "validation" / "validation_queries.sql").read_text(encoding="utf-8")
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        while cursor.description is None:
            cursor.nextset()
        columns = [c[0] for c in cursor.description]
        return pd.DataFrame.from_records(cursor.fetchall(), columns=columns).set_index("CaseName")
    finally:
        connection.close()


def slice_values(d: dict, f: kpis.Filters) -> dict:
    month = kpis.monthly(d, f).loc[f.month]
    actions = kpis.action_effect(kpis.scope(d["action"], f, by_priority=False)).iloc[0]
    return {"K1_Incidents": month["Incidents"], "K3_MttrHours": month["MTTR (h)"],
            "K4_SlaPct": month["SLA Compliance %"], "K5_RepeatPct": month["Repeat Rate %"],
            "K7_Backlog": month["OpenBacklog"], "K9_Before": actions["Before"], "K9_After": actions["After"]}


def circuit_values(d: dict, circuit_id: str) -> dict:
    history = kpis.add_rates(kpis.circuit_totals(d, circuit_id).to_frame().T).iloc[0]
    actions = kpis.action_effect(d["action"][d["action"]["CircuitId"] == circuit_id]).iloc[0]
    return {"K1_Incidents": history["Incidents"], "K3_MttrHours": history["MTTR (h)"],
            "K4_SlaPct": history["SLA Compliance %"], "K5_RepeatPct": history["Repeat Rate %"],
            "K7_Backlog": history["OpenBacklog"], "K9_Before": actions["Before"], "K9_After": actions["After"]}


@pytest.mark.parametrize("case", ["Month Dec 2025", "Region South, Dec 2025", "Circuit NG-FWA-001453, all months"])
def test_kpis_match_independent_sql(case, data, expected):
    if case.startswith("Circuit"):
        actual = circuit_values(data, "NG-FWA-001453")
    else:
        regions = ("South",) if "South" in case else ()
        actual = slice_values(data, kpis.Filters(month=202512, regions=regions))
    for kpi, tolerance in TOLERANCE.items():
        assert float(actual[kpi]) == pytest.approx(float(expected.loc[case, kpi]), abs=tolerance), kpi
