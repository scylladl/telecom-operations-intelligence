"""Midnight Ops pages: dark monitoring layout, HTML KPI tiles with 13-month sparklines, dense chart grid.
Same KPIs and rules as the classic design (kpis.py); only the presentation differs."""
from base64 import b64encode
from html import escape

import pandas as pd
import streamlit as st

import kpis
import narrative
import ui

# Colours validated with the dataviz palette script against the panel colour #131C2E (dark mode).
THEME = ui.Theme(
    series="#12A594", context="#33415C", ink="#E6EDF7", muted="#8B9BB4", grid="#1F2A3D", critical="#E5484D",
    categorical=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"),
    ordinal=("#0F766E", "#0D9488", "#2DD4BF", "#99F6E4"),  # on a dark panel the oldest bucket is the brightest
    heat=("#1B2A41", "#0F766E"), heat_text="#E6EDF7", surface="#131C2E",
)


def head(title: str, d: dict, f: kpis.Filters | None, headline: str | None = None) -> None:
    """Title, processing status and the filters in context, as one HTML strip."""
    status = d["status"].iloc[0]
    failed = status["LastRunStatus"] == "Failed"
    state = "Latest processing run failed" if failed else "Processing OK"
    chips = ""
    if f:
        values = [ui.month_label(d, f.month)] + [", ".join(v) if v else f"All {name}" for v, name in (
            (f.regions, "regions"), (f.technologies, "technologies"), (f.tiers, "tiers"), (f.priorities, "priorities"))]
        chips = '<div class="ng-chips">' + "".join(f'<span class="ng-chip">{escape(v)}</span>' for v in values) + "</div>"
    st.html(
        f'<div class="ng-head"><h1>{escape(title)}</h1>'
        f'<span class="ng-status"><span class="ng-dot{" failed" if failed else ""}"></span>{state} · '
        f'data as of {status["DataAsOfDate"]:%d %b %Y} · processed {status["LastSuccessAt"]:%d %b %Y %H:%M} · '
        f'simulated data</span></div>{chips}'
        + (f'<div class="ng-headline">{escape(headline)}</div>' if headline else "")
    )


def sparkline(values: pd.Series) -> str:
    """SVG of the 13-month window, the last point (the selected month) marked. Passed as a data URI image,
    because st.html sanitizes inline SVG away."""
    values = values.astype(float).dropna()
    if len(values) < 2:
        return ""
    width, height, pad = 180, 30, 3
    low, high = values.min(), values.max()
    span = (high - low) or 1
    points = [(pad + i * (width - 2 * pad) / (len(values) - 1), height - pad - (v - low) / span * (height - 2 * pad))
              for i, v in enumerate(values)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    x, y = points[-1]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
           f'<polyline points="{path}" fill="none" stroke="#5B6B86" stroke-width="1.5"/>'
           f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{THEME.series}"/></svg>')
    return (f'<img class="ng-spark" alt="" width="{width}" height="{height}" '
            f'src="data:image/svg+xml;base64,{b64encode(svg.encode()).decode()}">')


def tile(label: str, value: str, delta: str = "", good: bool | None = None, spark: str = "") -> str:
    tone = "" if good is None else (" good" if good else " bad")
    return (f'<div class="ng-tile"><div class="ng-label" title="{escape(label)}">{escape(label)}</div><div class="ng-value">{escape(value)}</div>'
            f'<span class="ng-delta{tone}">{delta}</span>{spark}</div>')


def kpi_tile(t: pd.DataFrame, f: kpis.Filters, name: str, label: str | None = None, kind: str | None = None,
             change_kind: str = "relative") -> str:
    """Tile for a column of the monthly table: value, change vs the prior month (arrow, sign and colour) and
    sparkline. Headline KPIs take polarity and format from kpis/ui; for the rest lower is better."""
    lower_is_better, change_kind = kpis.KPI_POLARITY.get(name, (True, change_kind))
    kind = kind or ui.KPI_FORMAT[name]
    current = t.loc[f.month, name]
    change = kpis.change(current, t[name].get(kpis.shift_month(f.month, -1), float("nan")), change_kind)
    delta, good = "", None
    if not pd.isna(change):
        arrow = "▲" if change > 0 else "▼" if change < 0 else "■"
        delta = f"{arrow} {ui.fmt(change, 'signed_pct' if change_kind == 'relative' else 'pp')} vs prior month"
        good = None if change == 0 else (change < 0) == lower_is_better
    return tile(label or name, ui.fmt(current, kind), delta, good, sparkline(kpis.last_months(t, f.month)[name]))


def tiles(*items: str) -> None:
    st.html('<div class="ng-tiles">' + "".join(items) + "</div>")


def context() -> tuple[dict, kpis.Filters, pd.DataFrame]:
    d = ui.load_data()
    f = st.session_state["filters"]
    return d, f, kpis.monthly(d, f)


def overview() -> None:
    d, f, t = context()
    head("Network operations", d, f, narrative.overview(d, f, t))
    tiles(*(kpi_tile(t, f, name) for name in kpis.KPI_POLARITY))
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.trend(t, f, "Incidents", "Incidents, last 13 months", "int", bars=True)
    with right, st.container(border=True):
        ui.trend(t, f, "SLA Compliance %", "SLA compliance %, last 13 months", "pct")
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.heatmap(kpis.tier_priority(d, f, "SLA Compliance %"), "SLA compliance % by tier and priority", "pct")
    with right, st.container(border=True):
        causes = kpis.opened_in(d, f).query("IsCounted == 1").pivot_table(
            index="Region", columns="RootCause", values="IsCounted", aggfunc="sum", fill_value=0)
        order = d["root_cause"].sort_values("SortOrder")["RootCause"]
        ui.stacked_bars(causes, [(c, c, color) for c, color in zip(order, THEME.categorical)],
                        "Root cause of incidents by region")


def sla() -> None:
    d, f, t = context()
    month = t.loc[f.month]
    head("SLA and restoration", d, f, narrative.sla(d, f, t))
    tiles(kpi_tile(t, f, "SLA Compliance %"), kpi_tile(t, f, "MTTR (h)"),
          tile("SLA in-scope tickets", ui.fmt(month["SlaInScope"], "int")),
          tile("SLA breaches", ui.fmt(month["SLA Breaches"], "int")))
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.ranked_bars(kpis.restoration_by(d, f, ["Region"]), "Region", "SLA Compliance %",
                       "SLA compliance % by region (lowest first)", "pct", lowest_first=True)
    with right, st.container(border=True):
        ui.heatmap(kpis.tier_priority(d, f, "MTTR (h)"), "MTTR (h) by tier and priority", "dec1")
    with st.container(border=True):
        st.markdown("**Worst 10 SLA breaches restored in the period**")
        worst = kpis.worst_breaches(d, f)
        ui.table(
            worst[["TicketId", "CircuitId", "CustomerName", "Region", "Tier", "PriorityCode",
                                       "RestoredAt", "SlaTargetHours", "RestoreHours", "HoursOverTarget"]],
            TicketId="Ticket", CircuitId="Circuit", CustomerName="Customer", PriorityCode="Priority",
            RestoredAt=st.column_config.DatetimeColumn("Restored", format="DD MMM YYYY HH:mm"),
            SlaTargetHours=st.column_config.NumberColumn("Target (h)", format="%.0f"),
            RestoreHours=st.column_config.NumberColumn("Restore (h)", format="%.1f"),
            HoursOverTarget=st.column_config.ProgressColumn(
                "Over target (h)", format="%.0f", min_value=0,
                max_value=float(max(worst["HoursOverTarget"].max(), 1))),
        )


def repeat() -> None:
    d, f, t = context()
    month = t.loc[f.month]
    head("Repeat and chronic circuits", d, f, narrative.repeat(d, f, t))
    tiles(kpi_tile(t, f, "Repeat Rate %"), tile("Repeat incidents", ui.fmt(month["RepeatIncidents"], "int")),
          kpi_tile(t, f, "Chronic Circuits", "Chronic circuits at month end", "int"))
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.trend(t, f, "Repeat Rate %", "Repeat rate %, last 13 months", "pct")
    with right, st.container(border=True):
        ui.ranked_bars(kpis.repeat_by(d, f, ["Technology"]), "Technology", "Repeat Rate %",
                       "Repeat rate % by technology (highest first)", "pct", lowest_first=False)
    chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
    with st.container(border=True):
        st.markdown("**Chronic circuits at the end of the period**")
        ui.table(
            chronic.sort_values(["TicketsInWindow", "LastOpenedAt"], ascending=False)[
                ["CircuitId", "CustomerName", "Region", "Technology", "Tier", "AccountManager", "TicketsInWindow",
                 "LastOpenedAt"]],
            CircuitId="Circuit", CustomerName="Customer", AccountManager="Account manager",
            TicketsInWindow=st.column_config.NumberColumn("Tickets in window", format="%d"),
            LastOpenedAt=st.column_config.DatetimeColumn("Last incident opened", format="DD MMM YYYY HH:mm"),
        )


def backlog() -> None:
    d, f, t = context()
    head("Backlog and aging", d, f, narrative.backlog(d, f, t))
    tiles(kpi_tile(t, f, "OpenBacklog", "Open backlog at month end", "int"),
          tile("Oldest open ticket (days)", ui.fmt(t.loc[f.month, "OldestDays"], "int")),
          kpi_tile(t, f, "Backlog Over 30 Days %", "Open more than 30 days", "pct", "pp"))
    open_tickets = kpis.snapshot(kpis.scope(d["backlog"], f), d, f)
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.trend(t, f, "OpenBacklog", "Open backlog at month end, last 13 months", "int", bars=True)
    with right, st.container(border=True):
        aging = open_tickets.pivot_table(index="Region", columns="AgeBucketCode", values="TicketId", aggfunc="size",
                                         fill_value=0)
        buckets = d["age_bucket"].sort_values("AgeBucketCode")
        ui.stacked_bars(aging, list(zip(buckets["AgeBucketCode"], buckets["AgeBucket"],
                                        THEME.ordinal + (THEME.critical,))), "Open backlog by region and age")
    with st.container(border=True):
        st.markdown("**Oldest open tickets at the end of the period**")
        ui.table(open_tickets.nlargest(10, "AgeDays")[["TicketId", "CircuitId", "CustomerName", "Region",
                                                       "Technology", "PriorityCode", "AgeDays"]],
                 TicketId="Ticket", CircuitId="Circuit", CustomerName="Customer", PriorityCode="Priority",
                 AgeDays=st.column_config.NumberColumn("Days open", format="%d"))


def actions() -> None:
    d, f, _ = context()
    actions = kpis.scope(d["action"], f, by_priority=False)
    total = kpis.action_effect(actions).iloc[0]
    head("Improvement actions", d, f, narrative.actions(total))
    st.caption(narrative.action_window(d))
    net = total["Net Action Effect (pp)"]
    tiles(tile("Actions evaluated", ui.fmt(total["Actions Evaluated"], "int")),
          tile("Before vs after", ui.fmt(total["Incident Change %"], "signed_pct")),
          tile("Control group change", ui.fmt(total["Control Change %"], "signed_pct")),
          tile("Net action effect", ui.fmt(net, "pp"), "negative = fewer incidents", None if pd.isna(net) else net < 0))
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.treated_vs_control(kpis.action_effect(actions, ["ActionType"]))
    with right, st.container(border=True):
        ui.net_effect_by(kpis.action_effect(actions, ["Region"]), "Region")


def data_quality() -> None:
    d, f, t = context()
    month = t.loc[f.month]
    checks = d["dq_check"]
    failed = int((checks["Result"] == "Fail").sum())
    head("Data quality", d, f, narrative.data_quality(d, f, t))
    tiles(kpi_tile(t, f, "Duplicates", "Duplicate tickets", "int"),
          tile("Duplicate share", ui.fmt(month["Duplicate Share %"], "pct")),
          tile("Cancelled tickets", ui.fmt(month["Cancelled"], "int")),
          tile("Failed checks", str(failed), "all checks pass" if failed == 0 else "see the table", failed == 0))
    left, right = st.columns(2)
    with left, st.container(border=True):
        ui.trend(t, f, "Duplicates", "Duplicate tickets (DPC), last 13 months", "int", bars=True)
    with right, st.container(border=True):
        st.markdown("**Checks run by dq.usp_RunChecks**")
        ui.table(checks[["CheckCode", "CheckName", "Result", "AffectedRows", "UnhandledRows"]],
                 CheckCode="Check", CheckName="Check name",
                 AffectedRows=st.column_config.NumberColumn("Affected", format="%d"),
                 UnhandledRows=st.column_config.NumberColumn("Unhandled", format="%d"))


def circuit() -> None:
    d = ui.load_data()
    f = st.session_state["filters"]
    head("Circuit detail", d, None)
    chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
    circuit_ids = d["circuit"]["CircuitId"].sort_values().tolist()
    default = chronic.nlargest(1, "TicketsInWindow")["CircuitId"].iloc[0] if not chronic.empty else circuit_ids[0]
    circuit_id = st.selectbox("Circuit (all months; the filters do not apply here)", circuit_ids,
                              index=circuit_ids.index(default))
    info = d["circuit"].set_index("CircuitId").loc[circuit_id]
    st.html(f'<div class="ng-info"><b>{escape(info["CustomerName"])}</b> · {escape(info["Segment"])} · '
            f'{escape(info["Tier"])} tier · {escape(info["Technology"])} · {escape(info["Region"])} '
            f'({escape(info["Province"])}) · account manager {escape(info["AccountManager"])}</div>')
    totals = kpis.add_rates(kpis.circuit_totals(d, circuit_id).to_frame().T).iloc[0]
    tiles(tile("Incidents", ui.fmt(totals["Incidents"], "int")), tile("MTTR (h)", ui.fmt(totals["MTTR (h)"], "dec1")),
          tile("Repeat rate", ui.fmt(totals["Repeat Rate %"], "pct")))
    with st.container(border=True):
        st.markdown("**Incident history (all tickets, including cancelled and duplicates)**")
        ui.table(
            kpis.circuit_history(d, circuit_id)[["TicketId", "IncidentClass", "PriorityCode", "RootCause", "OpenedAt",
                                                 "RestoredAt", "RestoreHours", "SlaTargetHours", "IsSlaMet",
                                                 "IsRepeat"]],
            TicketId="Ticket", IncidentClass="Class", PriorityCode="Priority", RootCause="Root cause",
            OpenedAt=st.column_config.DatetimeColumn("Opened", format="DD MMM YYYY HH:mm"),
            RestoredAt=st.column_config.DatetimeColumn("Restored", format="DD MMM YYYY HH:mm"),
            RestoreHours=st.column_config.NumberColumn("Restore (h)", format="%.1f"),
            SlaTargetHours=st.column_config.NumberColumn("Target (h)", format="%.0f"),
            IsSlaMet=st.column_config.CheckboxColumn("SLA met"),
            IsRepeat=st.column_config.CheckboxColumn("Repeat"),
        )
