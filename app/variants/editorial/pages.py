"""Editorial pages: one headline sentence per page, numbers in a line of text instead of boxes, one accent colour
for the selected month, small multiples. Same KPIs and rules as the classic design (kpis.py)."""
from dataclasses import replace
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import kpis
import narrative
import ui

# Colours validated with the dataviz palette script on white and on the paper colour.
THEME = ui.Theme(
    series="#009191", context="#D5CEC2", ink="#1F2328", muted="#5F6368", grid="#ECE7DE", critical="#C2410C",
    categorical=("#009191", "#8A8F98"),  # treated circuits vs comparable untreated circuits (grey = context)
    ordinal=("#6FB7BE", "#3E9AA3", "#1A7F89", "#00636C"),
    heat=("#E3F1F1", "#6FB7BE"), heat_text="#1F2328", surface="#F6F3EE",
)


def head(kicker: str, headline: str, d: dict, f: kpis.Filters | None) -> None:
    """Kicker (page and month), the page's headline sentence, and a standfirst with data status and filters."""
    status = d["status"].iloc[0]
    parts = [f"Data as of {status['DataAsOfDate']:%d %b %Y}", f"processed {status['LastSuccessAt']:%d %b %Y %H:%M}"]
    if status["LastRunStatus"] == "Failed":
        parts.append("warning: the latest processing run failed")
    parts.append("simulated data")
    if f:
        parts += [", ".join(v) if v else f"all {name}" for v, name in (
            (f.regions, "regions"), (f.technologies, "technologies"), (f.tiers, "tiers"), (f.priorities, "priorities"))]
        kicker = f"{kicker} · {ui.month_label(d, f.month)}"
    st.html(f'<div class="ed-kicker">{escape(kicker)}</div><div class="ed-headline">{escape(headline)}</div>'
            f'<div class="ed-standfirst">{escape(" · ".join(parts))}</div>')


def stat(value: str, label: str, change: str = "", good: bool | None = None) -> str:
    tone = "" if good is None else (" good" if good else " bad")
    return (f'<div class="ed-stat"><div class="ed-stat-value">{escape(value)}</div>'
            f'<div class="ed-stat-label">{escape(label)}</div>'
            f'<div class="ed-stat-change{tone}">{escape(change)}</div></div>')


def kpi_stat(d: dict, t: pd.DataFrame, f: kpis.Filters, name: str, label: str, kind: str | None = None,
             change_kind: str = "relative") -> str:
    """A KPI with its change vs the prior month written out ("▲ +8.7% vs Nov 2025"): sign and arrow, colour second."""
    lower_is_better, change_kind = kpis.KPI_POLARITY.get(name, (True, change_kind))
    prior = kpis.shift_month(f.month, -1)
    current = t.loc[f.month, name]
    change = kpis.change(current, t[name].get(prior, float("nan")), change_kind)
    if pd.isna(change):
        return stat(ui.fmt(current, kind or ui.KPI_FORMAT[name]), label)
    arrow = "▲" if change > 0 else "▼" if change < 0 else "■"
    text = f"{arrow} {ui.fmt(change, 'signed_pct' if change_kind == 'relative' else 'pp')} vs {ui.month_label(d, prior)}"
    return stat(ui.fmt(current, kind or ui.KPI_FORMAT[name]), label, text,
                None if change == 0 else (change < 0) == lower_is_better)


def stats(*items: str) -> None:
    st.html('<div class="ed-stats">' + "".join(items) + "</div>")


def section(title: str) -> None:
    st.html(f'<div class="ed-section">{escape(title)}</div>')


def context() -> tuple[dict, kpis.Filters, pd.DataFrame]:
    d = ui.load_data()
    f = st.session_state["filters"]
    return d, f, kpis.monthly(d, f)


def share_bars(counts: pd.Series, title: str) -> None:
    """Shares of a total as ranked bars; the largest is the accent, the rest are context."""
    counts = counts[counts > 0].sort_values()
    share = counts / counts.sum()
    fig = go.Figure(go.Bar(
        y=share.index, x=share, orientation="h",
        marker={"color": [THEME.context] * (len(share) - 1) + [THEME.series], "cornerradius": 3},
        text=[f"{v:.0%}" for v in share], textposition="outside", cliponaxis=False,
        customdata=counts, hovertemplate="%{y}: %{x:.1%} (%{customdata:,.0f} incidents)<extra></extra>",
    ))
    fig = ui.style(fig, title, height=max(220, 60 + 32 * len(share)))
    fig.update_xaxes(showticklabels=False, range=[0, share.max() * 1.18])
    fig.update_yaxes(showgrid=False)
    ui.show(fig)


def region_small_multiples(d: dict, f: kpis.Filters) -> None:
    """SLA compliance % by region over the 13-month window, one small chart per region on a shared scale."""
    regions = [r for r in sorted(d["circuit"]["Region"].unique()) if r != "Unknown" and (not f.regions or r in f.regions)]
    series = {r: kpis.last_months(kpis.monthly(d, replace(f, regions=(r,))), f.month)["SLA Compliance %"]
              for r in regions}
    columns = 3
    rows = -(-len(regions) // columns)
    fig = make_subplots(rows=rows, cols=columns, subplot_titles=regions, shared_yaxes=True,
                        horizontal_spacing=0.04, vertical_spacing=0.16)
    for i, region in enumerate(regions):
        values = series[region]
        row, col = i // columns + 1, i % columns + 1
        fig.add_trace(go.Scatter(x=list(range(len(values))), y=values, mode="lines", line={"color": THEME.context,
                                 "width": 2}, customdata=d["months"].loc[values.index, "MonthLabel"],
                                 hovertemplate=f"{region} · %{{customdata}}: %{{y:.1%}}<extra></extra>"), row, col)
        fig.add_trace(go.Scatter(x=[len(values) - 1], y=[values.iloc[-1]], mode="markers+text",
                                 marker={"color": THEME.series, "size": 8}, text=[f"{values.iloc[-1]:.0%}"],
                                 textposition="middle right", cliponaxis=False, hoverinfo="skip"), row, col)
    fig = ui.style(fig, "SLA compliance % by region, last 13 months (dot: selected month)", height=170 * rows + 70,
                   percent_axis=True)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(showticklabels=False, range=[-0.3, 14.5])  # room for the label right of the last point
    fig.update_annotations(font={"size": 12, "color": THEME.ink})
    ui.show(fig)


def before_after(effect: pd.DataFrame) -> None:
    """Dumbbell: incident change of treated circuits and of comparable untreated circuits, per action type.
    The gap between the two dots is the net effect of the action."""
    effect = effect.sort_values("Net Action Effect (pp)")
    fig = go.Figure()
    for _, row in effect.iterrows():
        fig.add_trace(go.Scatter(x=[row["Control Change %"], row["Treated Change % (Matched)"]],
                                 y=[row["ActionType"]] * 2, mode="lines", line={"color": THEME.context, "width": 3},
                                 hoverinfo="skip", showlegend=False))
    for column, label, color in (("Control Change %", "Comparable untreated circuits", THEME.categorical[1]),
                                 ("Treated Change % (Matched)", "Treated circuits", THEME.categorical[0])):
        fig.add_trace(go.Scatter(x=effect[column], y=effect["ActionType"], mode="markers", name=label,
                                 marker={"color": color, "size": 12},
                                 hovertemplate=f"%{{y}} · {label}: %{{x:+.1%}}<extra></extra>"))
    fig = ui.style(fig, "Incident change after the action: treated vs comparable circuits", height=320)
    fig.update_xaxes(tickformat="+.0%", showgrid=True, gridcolor=THEME.grid)
    fig.update_yaxes(showgrid=False)
    ui.show(fig)


def overview() -> None:
    d, f, t = context()
    with st.container(key="ed-page"):
        head("Overview", narrative.overview(d, f, t), d, f)
        stats(*(kpi_stat(d, t, f, name, name) for name in kpis.KPI_POLARITY))
        left, right = st.columns(2, gap="large")
        with left:
            ui.trend(t, f, "Incidents", "Incidents, last 13 months", "int", bars=True)
        with right:
            ui.trend(t, f, "SLA Compliance %", "SLA compliance %, last 13 months", "pct")
        section("What caused the incidents")
        counted = kpis.opened_in(d, f).query("IsCounted == 1")
        share_bars(counted.groupby("RootCause")["IsCounted"].sum(), "Share of incidents by root cause")


def sla() -> None:
    d, f, t = context()
    month = t.loc[f.month]
    with st.container(key="ed-page"):
        head("SLA and restoration", narrative.sla(d, f, t), d, f)
        stats(kpi_stat(d, t, f, "SLA Compliance %", "SLA compliance"), kpi_stat(d, t, f, "MTTR (h)", "MTTR (hours)"),
              stat(ui.fmt(month["SlaInScope"], "int"), "tickets in SLA scope"),
              stat(ui.fmt(month["SLA Breaches"], "int"), "breaches"))
        region_small_multiples(d, f)
        left, right = st.columns(2, gap="large")
        with left:
            ui.heatmap(kpis.tier_priority(d, f, "SLA Compliance %"), "SLA compliance % by tier and priority", "pct")
        with right:
            ui.ranked_bars(kpis.restoration_by(d, f, ["Technology"]), "Technology", "SLA Compliance %",
                           "SLA compliance % by technology (lowest first)", "pct", lowest_first=True)
        section("The ten worst breaches restored this month")
        ui.table(kpis.worst_breaches(d, f)[["TicketId", "CustomerName", "Region", "Tier", "PriorityCode",
                                            "SlaTargetHours", "RestoreHours", "HoursOverTarget"]],
                 TicketId="Ticket", CustomerName="Customer", PriorityCode="Priority",
                 SlaTargetHours=st.column_config.NumberColumn("Target (h)", format="%.0f"),
                 RestoreHours=st.column_config.NumberColumn("Restore (h)", format="%.1f"),
                 HoursOverTarget=st.column_config.NumberColumn("Over target (h)", format="%.1f"))


def repeat() -> None:
    d, f, t = context()
    month = t.loc[f.month]
    with st.container(key="ed-page"):
        head("Repeat and chronic", narrative.repeat(d, f, t), d, f)
        stats(kpi_stat(d, t, f, "Repeat Rate %", "repeat rate"),
              stat(ui.fmt(month["RepeatIncidents"], "int"), "repeat incidents"),
              kpi_stat(d, t, f, "Chronic Circuits", "chronic circuits at month end", "int"))
        left, right = st.columns(2, gap="large")
        with left:
            ui.trend(t, f, "Repeat Rate %", "Repeat rate %, last 13 months", "pct")
        with right:
            ui.ranked_bars(kpis.repeat_by(d, f, ["Technology"]), "Technology", "Repeat Rate %",
                           "Repeat rate % by technology (highest first)", "pct", lowest_first=False)
        section("Chronic circuits at month end")
        chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
        ui.table(chronic.sort_values(["TicketsInWindow", "LastOpenedAt"], ascending=False)[
                     ["CircuitId", "CustomerName", "Region", "Technology", "Tier", "TicketsInWindow"]],
                 CircuitId="Circuit", CustomerName="Customer",
                 TicketsInWindow=st.column_config.NumberColumn("Tickets in window", format="%d"))


def backlog() -> None:
    d, f, t = context()
    with st.container(key="ed-page"):
        head("Backlog and aging", narrative.backlog(d, f, t), d, f)
        stats(kpi_stat(d, t, f, "OpenBacklog", "tickets open at month end", "int"),
              stat(ui.fmt(t.loc[f.month, "OldestDays"], "int"), "days open, oldest ticket"),
              kpi_stat(d, t, f, "Backlog Over 30 Days %", "open more than 30 days", "pct", "pp"))
        open_tickets = kpis.snapshot(kpis.scope(d["backlog"], f), d, f)
        left, right = st.columns(2, gap="large")
        with left:
            ui.trend(t, f, "OpenBacklog", "Open backlog at month end, last 13 months", "int", bars=True)
        with right:
            aging = open_tickets.pivot_table(index="Region", columns="AgeBucketCode", values="TicketId",
                                             aggfunc="size", fill_value=0)
            buckets = d["age_bucket"].sort_values("AgeBucketCode")
            ui.stacked_bars(aging, list(zip(buckets["AgeBucketCode"], buckets["AgeBucket"],
                                            THEME.ordinal + (THEME.critical,))), "Open backlog by region and age")
        section("Oldest open tickets")
        ui.table(open_tickets.nlargest(10, "AgeDays")[["TicketId", "CustomerName", "Region", "PriorityCode",
                                                       "AgeDays"]],
                 TicketId="Ticket", CustomerName="Customer", PriorityCode="Priority",
                 AgeDays=st.column_config.NumberColumn("Days open", format="%d"))


def actions() -> None:
    d, f, _ = context()
    actions = kpis.scope(d["action"], f, by_priority=False)
    total = kpis.action_effect(actions).iloc[0]
    with st.container(key="ed-page"):
        head("Improvement actions", narrative.actions(total), d, None)
        stats(stat(ui.fmt(total["Actions Evaluated"], "int"), "actions evaluated"),
              stat(ui.fmt(total["Incident Change %"], "signed_pct"), "incidents, before vs after (as requested)"),
              stat(ui.fmt(total["Control Change %"], "signed_pct"), "comparable circuits without an action"),
              stat(ui.fmt(total["Net Action Effect (pp)"], "pp"), "net effect of the actions"))
        st.html(f'<p class="ed-note">{escape(narrative.action_window(d))}</p>')
        left, right = st.columns(2, gap="large")
        with left:
            before_after(kpis.action_effect(actions, ["ActionType"]))
        with right:
            ui.net_effect_by(kpis.action_effect(actions, ["Region"]), "Region")


def data_quality() -> None:
    d, f, t = context()
    month = t.loc[f.month]
    checks = d["dq_check"]
    with st.container(key="ed-page"):
        head("Data quality", narrative.data_quality(d, f, t), d, f)
        stats(kpi_stat(d, t, f, "Duplicates", "duplicate tickets", "int"),
              stat(ui.fmt(month["Duplicate Share %"], "pct"), "of valid plus duplicate tickets"),
              stat(ui.fmt(month["Cancelled"], "int"), "cancelled tickets"),
              stat(str(int((checks["Result"] == "Fail").sum())), "failed checks"))
        ui.trend(t, f, "Duplicates", "Duplicate tickets (DPC) by month, last 13 months", "int", bars=True)
        section("Checks run by dq.usp_RunChecks")
        ui.table(checks[["CheckCode", "CheckName", "Result", "AffectedRows", "Handling"]],
                 CheckCode="Check", CheckName="Check name",
                 AffectedRows=st.column_config.NumberColumn("Affected rows", format="%d"))


def circuit() -> None:
    d = ui.load_data()
    f = st.session_state["filters"]
    chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
    circuit_ids = d["circuit"]["CircuitId"].sort_values().tolist()
    default = chronic.nlargest(1, "TicketsInWindow")["CircuitId"].iloc[0] if not chronic.empty else circuit_ids[0]
    with st.container(key="ed-page"):
        circuit_id = st.selectbox("Circuit", circuit_ids, index=circuit_ids.index(default))
        info = d["circuit"].set_index("CircuitId").loc[circuit_id]
        totals = kpis.add_rates(kpis.circuit_totals(d, circuit_id).to_frame().T).iloc[0]
        head("Circuit detail", f"{circuit_id}: {totals['Incidents']:.0f} incidents since the data starts, "
                               f"repeat rate {ui.fmt(totals['Repeat Rate %'], 'pct')}.", d, None)
        stats(stat(ui.fmt(totals["Incidents"], "int"), "incidents"),
              stat(ui.fmt(totals["MTTR (h)"], "dec1"), "MTTR (hours)"),
              stat(str(info["CustomerName"]), f"{info['Segment']} · {info['Tier']} tier"),
              stat(str(info["Technology"]), f"{info['Region']} ({info['Province']})"))
        section("Every ticket of the circuit, cancelled and duplicates included")
        ui.table(kpis.circuit_history(d, circuit_id)[["TicketId", "IncidentClass", "PriorityCode", "RootCause",
                                                      "OpenedAt", "RestoreHours", "IsSlaMet", "IsRepeat"]],
                 TicketId="Ticket", IncidentClass="Class", PriorityCode="Priority", RootCause="Root cause",
                 OpenedAt=st.column_config.DatetimeColumn("Opened", format="DD MMM YYYY HH:mm"),
                 RestoreHours=st.column_config.NumberColumn("Restore (h)", format="%.1f"),
                 IsSlaMet=st.column_config.CheckboxColumn("SLA met"),
                 IsRepeat=st.column_config.CheckboxColumn("Repeat"))
