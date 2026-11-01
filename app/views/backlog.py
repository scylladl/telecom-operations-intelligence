import streamlit as st

import kpis
import narrative
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
month = t.loc[f.month]
open_tickets = kpis.snapshot(kpis.scope(d["backlog"], f), d, f)

ui.header("Backlog and Aging", d, f, narrative.backlog(d, f, t))

backlog, oldest, over_30 = st.columns(3)
prior = t["OpenBacklog"].get(kpis.shift_month(f.month, -1))
ui.metric(backlog, "Open backlog at month end", month["OpenBacklog"], "int",
          kpis.change(month["OpenBacklog"], prior, "relative"), "signed_pct")
ui.metric(oldest, "Oldest open ticket (days)", month["OldestDays"], "int")
ui.metric(over_30, "Open more than 30 days", month["Backlog Over 30 Days %"], "pct")

left, right = st.columns(2)
with left:
    ui.trend(t, f, "OpenBacklog", "Open backlog at month end, last 13 months", "int", bars=True)
with right:
    aging = open_tickets.pivot_table(index="Region", columns="AgeBucketCode", values="TicketId", aggfunc="size",
                                     fill_value=0)
    buckets = d["age_bucket"].sort_values("AgeBucketCode")
    colors = ui.theme.ordinal + (ui.theme.critical,)
    ui.stacked_bars(aging, list(zip(buckets["AgeBucketCode"], buckets["AgeBucket"], colors)),
                    "Open backlog by region and age")

st.subheader("Oldest open tickets at the end of the period")
ui.table(
    open_tickets.nlargest(10, "AgeDays")[["TicketId", "CircuitId", "CustomerName", "Region", "Technology",
                                          "PriorityCode", "AgeDays"]],
)
