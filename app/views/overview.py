import pandas as pd
import streamlit as st

import kpis
import narrative
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
prior, last_year = kpis.shift_month(f.month, -1), kpis.shift_month(f.month, -12)


def value(name: str, month: int) -> float:
    return t[name].get(month, float("nan"))


ui.header("Overview", d, f, narrative.overview(d, f, t))
for column, name in zip(st.columns(len(kpis.KPI_POLARITY)), kpis.KPI_POLARITY):
    ui.kpi_card(column, t, f, name)

# KPI scorecard: the Time Comparison calculation group of the Power BI model
rows = []
for name, (_, kind) in kpis.KPI_POLARITY.items():
    current, pm, ly = value(name, f.month), value(name, prior), value(name, last_year)
    change_format = "signed_pct" if kind == "relative" else "pp"
    rows.append({
        "KPI": name,
        "Selected month": ui.fmt(current, ui.KPI_FORMAT[name]),
        "Prior month": ui.fmt(pm, ui.KPI_FORMAT[name]),
        "MoM": ui.fmt(kpis.change(current, pm, kind), change_format),
        "Same month LY": ui.fmt(ly, ui.KPI_FORMAT[name]),
        "YoY": ui.fmt(kpis.change(current, ly, kind), change_format),
    })
st.subheader("KPI scorecard")
ui.table(pd.DataFrame(rows))

left, right = st.columns(2)
with left:
    ui.trend(t, f, "Incidents", "Incidents, last 13 months", "int", bars=True)
with right:
    ui.trend(t, f, "SLA Compliance %", "SLA compliance %, last 13 months", "pct")

causes = (
    kpis.opened_in(d, f).query("IsCounted == 1")
    .pivot_table(index="Region", columns="RootCause", values="IsCounted", aggfunc="sum", fill_value=0)
)
# colour follows the root cause in its fixed sort order, so a filter never repaints the survivors
causes_in_order = d["root_cause"].sort_values("SortOrder")["RootCause"]
ui.stacked_bars(causes, [(c, c, color) for c, color in zip(causes_in_order, ui.theme.categorical)],
                "Root cause of incidents by region")
