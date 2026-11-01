import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
month = t.loc[f.month]
repeat_days = d["kpi_parameter"].set_index("ParameterCode").loc["REPEAT_WINDOW_DAYS", "ParameterValue"]

chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
headline = (
    f"{ui.month_label(d, f.month)}: {ui.fmt(month['Repeat Rate %'], 'pct')} of incidents hit a circuit restored in the "
    f"previous {repeat_days:.0f} days. {ui.fmt(month['Chronic Circuits'], 'int')} circuits are chronic at month end"
)
headline += f", most of them {chronic['Technology'].mode().iloc[0]}." if not chronic.empty else "."
ui.header("Repeat and Chronic", d, f, headline)

repeat_rate, repeats, chronic_count = st.columns(3)
ui.kpi_card(repeat_rate, t, f, "Repeat Rate %")
ui.metric(repeats, "Repeat incidents", month["RepeatIncidents"], "int")
ui.metric(chronic_count, "Chronic circuits at month end", month["Chronic Circuits"], "int")

left, right = st.columns(2)
with left:
    ui.trend(t, f, "Repeat Rate %", "Repeat rate %, last 13 months", "pct")
with right:
    ui.ranked_bars(kpis.repeat_by(d, f, ["Technology"]), "Technology", "Repeat Rate %",
                   "Repeat rate % by technology (highest first)", "pct", lowest_first=False)

st.subheader("Chronic circuits at the end of the period")
st.caption("Open a circuit's full history on the Circuit Detail page.")
ui.table(
    chronic.sort_values(["TicketsInWindow", "LastOpenedAt"], ascending=False)[
        ["CircuitId", "CustomerName", "Region", "Technology", "Tier", "AccountManager", "TicketsInWindow",
         "LastOpenedAt"]],
    CircuitId="Circuit", CustomerName="Customer", AccountManager="Account manager",
    TicketsInWindow=st.column_config.NumberColumn("Tickets in window", format="%d"),
    LastOpenedAt=st.column_config.DatetimeColumn("Last incident opened", format="DD MMM YYYY HH:mm"),
)
