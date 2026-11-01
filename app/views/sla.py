import streamlit as st

import kpis
import narrative
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
month = t.loc[f.month]

by_region = kpis.restoration_by(d, f, ["Region"])
ui.header("SLA and Restoration", d, f, narrative.sla(d, f, t))

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

left, right = st.columns(2)
with left:
    ui.heatmap(kpis.tier_priority(d, f, "SLA Compliance %"), "SLA compliance % by tier and priority", "pct")
with right:
    ui.heatmap(kpis.tier_priority(d, f, "MTTR (h)"), "MTTR (h) by tier and priority", "dec1")

st.subheader("Worst 10 SLA breaches restored in the period")
worst = kpis.worst_breaches(d, f)
ui.table(
    worst[["TicketId", "CircuitId", "CustomerName", "Region", "Tier", "PriorityCode", "RestoredAt",
           "SlaTargetHours", "RestoreHours", "HoursOverTarget"]],
)
