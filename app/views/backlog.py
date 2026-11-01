import plotly.graph_objects as go
import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
month = t.loc[f.month]
open_tickets = kpis.snapshot(kpis.scope(d["backlog"], f), d, f)

headline = (
    f"End of {ui.month_label(d, f.month)}: {ui.fmt(month['OpenBacklog'], 'int')} tickets open, the oldest for "
    f"{ui.fmt(month['OldestDays'], 'int')} days; {ui.fmt(month['Backlog Over 30 Days %'], 'pct')} open for more than 30 days."
)
ui.header("Backlog and Aging", d, f, headline)

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
    aging = aging.loc[aging.sum(axis=1).sort_values().index]
    buckets = d["age_bucket"].sort_values("AgeBucketCode")
    colors = dict(zip(buckets["AgeBucketCode"], ui.ORDINAL + [ui.CRITICAL]))
    fig = go.Figure([
        go.Bar(y=aging.index, x=aging[code], name=name, orientation="h",
               marker={"color": colors[code], "line": {"color": "white", "width": 1}},
               hovertemplate=f"%{{y}} · {name}: %{{x:,.0f}}<extra></extra>")
        for code, name in zip(buckets["AgeBucketCode"], buckets["AgeBucket"]) if code in aging.columns
    ])
    fig.update_layout(barmode="stack")
    ui.show(ui.style(fig, "Open backlog by region and age", height=max(320, 120 + 34 * len(aging))))

st.subheader("Oldest open tickets at the end of the period")
ui.table(
    open_tickets.nlargest(10, "AgeDays")[["TicketId", "CircuitId", "CustomerName", "Region", "Technology",
                                          "PriorityCode", "AgeDays"]],
    TicketId="Ticket", CircuitId="Circuit", CustomerName="Customer", PriorityCode="Priority",
    AgeDays=st.column_config.NumberColumn("Days open", format="%d"),
)
