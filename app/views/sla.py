import plotly.graph_objects as go
import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
month = t.loc[f.month]

by_region = kpis.restoration_by(d, f, ["Region"])
known = by_region[by_region["Region"] != "Unknown"].dropna(subset=["SLA Compliance %"])
headline = (
    f"{ui.month_label(d, f.month)}: {ui.fmt(month['SLA Compliance %'], 'pct')} of in-scope tickets restored within "
    f"target ({ui.fmt(month['SLA Breaches'], 'int')} breaches)."
)
if not known.empty:
    worst = known.nsmallest(1, "SLA Compliance %").iloc[0]
    headline += f" Lowest region: {worst['Region']} at {ui.fmt(worst['SLA Compliance %'], 'pct')}."
ui.header("SLA and Restoration", d, f, headline)

sla, mttr, in_scope, breaches = st.columns(4)
ui.kpi_card(sla, t, f, "SLA Compliance %")
ui.kpi_card(mttr, t, f, "MTTR (h)")
ui.metric(in_scope, "SLA in-scope tickets", month["SlaInScope"], "int")
ui.metric(breaches, "SLA breaches", month["SLA Breaches"], "int")

left, right = st.columns(2)
with left:
    ui.ranked_bars(by_region, "Region", "SLA Compliance %", "SLA compliance % by region (lowest first)", "pct",
                   lowest_first=True)
with right:
    ui.ranked_bars(kpis.restoration_by(d, f, ["Technology"]), "Technology", "SLA Compliance %",
                   "SLA compliance % by technology (lowest first)", "pct", lowest_first=True)


# Sequential blue, darker means a larger value; light enough at the top for dark cell labels.
HEAT_SCALE = [[0, "#cde2fb"], [1, "#5598e7"]]


def tier_priority_heatmap(measure: str, title: str, kind: str) -> None:
    grid = kpis.restoration_by(d, f, ["TierSort", "Tier", "PriorityCode"]).pivot_table(
        index=["TierSort", "Tier"], columns="PriorityCode", values=measure)
    grid.index = grid.index.get_level_values("Tier")
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=grid.columns, y=grid.index, colorscale=HEAT_SCALE, showscale=False, xgap=2, ygap=2,
        text=[[ui.fmt(v, kind) for v in row] for row in grid.values], texttemplate="%{text}",
        hovertemplate="%{y} · %{x}: %{text}<extra></extra>",
    ))
    fig = ui.style(fig, title, height=260)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    ui.show(fig)


left, right = st.columns(2)
with left:
    tier_priority_heatmap("SLA Compliance %", "SLA compliance % by tier and priority", "pct")
with right:
    tier_priority_heatmap("MTTR (h)", "MTTR (h) by tier and priority", "dec1")

st.subheader("Worst 10 SLA breaches restored in the period")
worst = kpis.worst_breaches(d, f)
ui.table(
    worst[["TicketId", "CircuitId", "CustomerName", "Region", "Tier", "PriorityCode", "RestoredAt",
           "SlaTargetHours", "RestoreHours", "HoursOverTarget"]],
    TicketId="Ticket", CircuitId="Circuit", CustomerName="Customer", PriorityCode="Priority",
    RestoredAt=st.column_config.DatetimeColumn("Restored", format="DD MMM YYYY HH:mm"),
    SlaTargetHours=st.column_config.NumberColumn("Target (h)", format="%.0f"),
    RestoreHours=st.column_config.NumberColumn("Restore (h)", format="%.1f"),
    HoursOverTarget=st.column_config.NumberColumn("Over target (h)", format="%.1f"),
)
