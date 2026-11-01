import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
prior, last_year = kpis.shift_month(f.month, -1), kpis.shift_month(f.month, -12)


def value(name: str, month: int) -> float:
    return t[name].get(month, float("nan"))


headline = (
    f"{ui.month_label(d, f.month)}: {ui.fmt(value('Incidents', f.month), 'int')} incidents "
    f"({ui.fmt(kpis.change(value('Incidents', f.month), value('Incidents', prior), 'relative'), 'signed_pct')} vs prior month), "
    f"SLA compliance {ui.fmt(value('SLA Compliance %', f.month), 'pct')} "
    f"({ui.fmt(kpis.change(value('SLA Compliance %', f.month), value('SLA Compliance %', prior), 'pp'), 'pp')}), "
    f"repeat rate {ui.fmt(value('Repeat Rate %', f.month), 'pct')} "
    f"({ui.fmt(kpis.change(value('Repeat Rate %', f.month), value('Repeat Rate %', prior), 'pp'), 'pp')})."
)
ui.header("Overview", d, f, headline)
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
colors = dict(zip(d["root_cause"].sort_values("SortOrder")["RootCause"], ui.CATEGORICAL))
causes = causes.loc[causes.sum(axis=1).sort_values().index]
fig = go.Figure([
    go.Bar(y=causes.index, x=causes[cause], name=cause, orientation="h",
           marker={"color": color, "line": {"color": "white", "width": 1}},
           hovertemplate=f"%{{y}} · {cause}: %{{x:,.0f}}<extra></extra>")
    for cause, color in colors.items() if cause in causes.columns
])
fig.update_layout(barmode="stack")
ui.show(ui.style(fig, "Root cause of incidents by region", height=360))
