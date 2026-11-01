"""Shared page parts: data loading, the report filters, page header, KPI cards and chart styling."""
import logging
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
import sqlalchemy as sa
import streamlit as st

import db
import kpis

@dataclass(frozen=True)
class Theme:
    """Chart colours of one design. Each design runs as its own Streamlit server, which sets its theme once."""
    series: str  # the measure in focus
    context: str  # everything else: other months, axis lines
    ink: str
    muted: str
    grid: str
    critical: str  # alert colour, only for the more-than-30-days backlog (project rule)
    categorical: tuple[str, ...]
    ordinal: tuple[str, ...]  # age buckets up to 30 days
    heat: tuple[str, str]  # sequential scale, darker means a larger value
    heat_text: str
    surface: str  # chart background: gaps between stacked segments, hover labels


# Reference palette of the dataviz method (validated for colour vision deficiency, adjacent pairs).
CLASSIC = Theme(
    series="#2a78d6", context="#c3c2b7", ink="#0b0b0b", muted="#52514e", grid="#e1e0d9", critical="#d03b3b",
    categorical=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"),
    ordinal=("#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"), heat=("#cde2fb", "#5598e7"), heat_text="#0b0b0b", surface="white",
)
theme = CLASSIC


def set_theme(new_theme: Theme) -> None:
    global theme
    theme = new_theme


@st.cache_resource
def _engine():
    return db.create_engine()


# The data changes once a day (database/refresh.ps1); a 15-minute cache keeps pages fast and still
# picks up a new processing run without restarting the app.
@st.cache_data(ttl=900, show_spinner="Loading data from SQL Server...")
def _load_data() -> dict:
    return kpis.prepare(db.read_views(_engine()))


def load_data() -> dict:
    try:
        return _load_data()
    except sa.exc.DBAPIError:
        logging.exception("Loading the rpt views failed")
        st.error("The database is not reachable right now. Check that SQL Server is running and that the "
                 "settings in app/.env are right; the server log has the details.")
        st.stop()


def filter_controls(d: dict, slots=None) -> kpis.Filters:
    """The five report-level filters of the Power BI report, shared by every page. slots holds one container
    per control (month, region, technology, tier, priority); the sidebar by default."""
    months = d["months"]
    circuit = d["circuit"]
    month_slot, region_slot, technology_slot, tier_slot, priority_slot = slots or [st.sidebar] * 5
    month = month_slot.selectbox("Month", months.index[::-1], format_func=lambda m: months.loc[m, "MonthLabel"],
                                 key="month")
    regions = region_slot.multiselect("Region", sorted(circuit["Region"].unique()), key="regions")
    technologies = technology_slot.multiselect("Technology", sorted(circuit["Technology"].unique()),
                                               key="technologies")
    tiers = tier_slot.multiselect("Tier", circuit.drop_duplicates("Tier").sort_values("TierSort")["Tier"],
                                  key="tiers")
    priorities = priority_slot.multiselect("Priority", d["priority"].sort_values("SortOrder")["PriorityCode"],
                                           key="priorities")
    return kpis.Filters(int(month), tuple(regions), tuple(technologies), tuple(tiers), tuple(priorities))


def month_label(d: dict, month: int) -> str:
    return d["months"].loc[month, "MonthLabel"]


def header(title: str, d: dict, f: kpis.Filters | None, headline: str | None = None) -> None:
    """Page title, data status (FR-09) and the filters in context; f is None on pages the filters do not reach."""
    status = d["status"].iloc[0]
    lines = [f"Data as of {status['DataAsOfDate']:%d %b %Y}", f"Processed {status['LastSuccessAt']:%d %b %Y %H:%M}"]
    if status["LastRunStatus"] == "Failed":
        lines.append("Warning: the latest processing run failed")
    lines.append("Simulated data")
    caption = "  |  ".join(lines)
    if f:
        context = [month_label(d, f.month)] + [", ".join(v) if v else f"All {name}" for v, name in (
            (f.regions, "regions"), (f.technologies, "technologies"), (f.tiers, "tiers"), (f.priorities, "priorities"))]
        caption += "  \n" + "  ·  ".join(context)

    st.title(title)
    st.caption(caption)
    if headline:
        st.markdown(f"**{headline}**")


def fmt(value: float, kind: str) -> str:
    if pd.isna(value):
        return "–"
    return {
        "int": f"{value:,.0f}",
        "dec1": f"{value:,.1f}",
        "dec2": f"{value:,.2f}",
        "pct": f"{value:.1%}",
        "signed_pct": f"{value:+.1%}",
        "pp": f"{value:+.1f} pp",
    }[kind]


def metric(column, label: str, value: float, kind: str, delta: float | None = None, delta_kind: str = "",
           lower_is_better: bool = True) -> None:
    """A KPI card; the change vs the prior month carries a sign and an arrow, never colour alone."""
    column.metric(
        label, fmt(value, kind),
        delta=None if delta is None or pd.isna(delta) else fmt(delta, delta_kind),
        delta_color="inverse" if lower_is_better else "normal",
        help=None if delta is None else "Change vs the prior month",
        border=True,
    )


KPI_FORMAT = {"Incidents": "int", "Incidents per 100 Circuits": "dec2", "MTTR (h)": "dec1",
              "SLA Compliance %": "pct", "Repeat Rate %": "pct"}


def kpi_card(column, table: pd.DataFrame, f: kpis.Filters, name: str) -> None:
    """Card for a headline KPI of the monthly table, compared with the prior month."""
    lower_is_better, change_kind = kpis.KPI_POLARITY[name]
    current = table.loc[f.month, name]
    previous = table[name].get(kpis.shift_month(f.month, -1), float("nan"))
    metric(column, name, current, KPI_FORMAT[name], kpis.change(current, previous, change_kind),
           "signed_pct" if change_kind == "relative" else "pp", lower_is_better)


def style(fig: go.Figure, title: str, height: int = 320, percent_axis: bool = False) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"size": 15, "color": theme.ink}, "x": 0, "xanchor": "left"},
        height=height, margin={"l": 8, "r": 8, "t": 48, "b": 8},
        font={"family": 'system-ui, -apple-system, "Segoe UI", sans-serif', "size": 12, "color": theme.muted},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={"bgcolor": theme.surface, "font_color": theme.ink},
        legend={"orientation": "h", "yanchor": "top", "y": -0.08, "x": 0, "title": None, "traceorder": "normal"},
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, linecolor=theme.context, ticks="", title=None, automargin=True)
    fig.update_yaxes(gridcolor=theme.grid, zeroline=False, linecolor=theme.context, title=None, automargin=True,
                     tickformat=".0%" if percent_axis else ",")
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def trend(table: pd.DataFrame, f: kpis.Filters, column: str, title: str, kind: str, bars: bool = False) -> None:
    """The 13-month window ending in the selected month; the selected month is labelled, the rest is context."""
    window = kpis.last_months(table, f.month)
    labels = window["MonthLabel"]
    text_format = {"int": "%{y:,.0f}", "pct": "%{y:.1%}", "dec1": "%{y:,.1f}"}[kind]
    if bars:
        colors = [theme.series if m == f.month else theme.context for m in window.index]
        fig = go.Figure(go.Bar(x=labels, y=window[column], marker={"color": colors, "cornerradius": 4},
                               hovertemplate=f"%{{x}}: {text_format}<extra></extra>"))
    else:
        fig = go.Figure(go.Scatter(x=labels, y=window[column], mode="lines+markers",
                                   line={"color": theme.series, "width": 2}, marker={"size": 8, "color": theme.series},
                                   hovertemplate=f"%{{x}}: {text_format}<extra></extra>"))
    last = window.iloc[-1]
    fig.add_annotation(x=last["MonthLabel"], y=last[column], text=fmt(last[column], kind), showarrow=False,
                       yshift=14, font={"color": theme.ink, "size": 12})
    fig = style(fig, title, percent_axis=kind == "pct")
    fig.update_xaxes(tickangle=0, nticks=7)
    show(fig)


def ranked_bars(df: pd.DataFrame, category: str, value: str, title: str, kind: str, lowest_first: bool) -> None:
    """Horizontal bars, the category to look at first on top; every bar carries its value."""
    # plotly draws the first row at the bottom
    df = df.dropna(subset=[value]).sort_values(value, ascending=not lowest_first)
    fig = go.Figure(go.Bar(y=df[category], x=df[value], orientation="h", marker={"color": theme.series, "cornerradius": 4},
                           text=[fmt(v, kind) for v in df[value]], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    fig = style(fig, title, height=max(220, 60 + 34 * len(df)))
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, df[value].max() * 1.15])  # room for labels
    fig.update_yaxes(showgrid=False)
    show(fig)


def stacked_bars(table: pd.DataFrame, series: list[tuple], title: str) -> None:
    """Horizontal stacked bars, largest category on top. series: (column, label, colour) in stack order."""
    table = table.loc[table.sum(axis=1).sort_values().index]
    fig = go.Figure([
        go.Bar(y=table.index, x=table[column], name=label, orientation="h",
               marker={"color": color, "line": {"color": theme.surface, "width": 1}},
               hovertemplate=f"%{{y}} · {label}: %{{x:,.0f}}<extra></extra>")
        for column, label, color in series if column in table.columns
    ])
    fig.update_layout(barmode="stack")
    show(style(fig, title, height=max(320, 120 + 34 * len(table))))


def heatmap(grid: pd.DataFrame, title: str, kind: str) -> None:
    """Values of a two-way table on a sequential scale, each cell labelled."""
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=grid.columns, y=grid.index, colorscale=[[0, theme.heat[0]], [1, theme.heat[1]]],
        showscale=False, xgap=2, ygap=2, text=[[fmt(v, kind) for v in row] for row in grid.values],
        texttemplate="%{text}", textfont={"color": theme.heat_text},
        hovertemplate="%{y} · %{x}: %{text}<extra></extra>",
    ))
    fig = style(fig, title, height=260)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    show(fig)


def treated_vs_control(by_type: pd.DataFrame) -> None:
    """K9 by action type: incident change on treated circuits next to comparable untreated circuits."""
    by_type = by_type.sort_values("Net Action Effect (pp)")
    fig = go.Figure([
        go.Bar(y=by_type["ActionType"], x=by_type[column], name=label, orientation="h",
               marker={"color": color, "cornerradius": 4},
               text=[fmt(v, "signed_pct") for v in by_type[column]], textposition="inside",
               insidetextanchor="start", textfont={"color": "white"},
               hovertemplate=f"%{{y}} · {label}: %{{text}}<extra></extra>")
        for column, label, color in (("Treated Change % (Matched)", "Treated circuits", theme.categorical[0]),
                                     ("Control Change %", "Comparable untreated circuits", theme.categorical[1]))
    ])
    fig.update_layout(barmode="group")
    fig = style(fig, "Incident change after the action vs comparable circuits", height=360)
    fig.update_xaxes(tickformat=".0%")
    show(fig)


def net_effect_by(effect: pd.DataFrame, category: str) -> None:
    """Net action effect in percentage points; negative is good: incidents fell beyond the natural decline."""
    effect = effect.dropna(subset=["Net Action Effect (pp)"]).sort_values("Net Action Effect (pp)", ascending=False)
    values = effect["Net Action Effect (pp)"]
    fig = go.Figure(go.Bar(
        y=effect[category], x=values, orientation="h",
        marker={"color": [theme.series if v < 0 else theme.critical for v in values], "cornerradius": 4},
        text=[fmt(v, "pp") for v in values], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig = style(fig, f"Net action effect (pp) by {category.lower()}, negative = fewer incidents", height=360)
    spread = values.abs().max() * 1.35  # room for the labels on both sides
    fig.update_xaxes(zeroline=True, zerolinecolor=theme.muted, range=[-spread, spread])
    show(fig)


_DATETIME = "DD MMM YYYY HH:mm"
_AVG_CONTROL = "Average incidents per control circuit"

# Display name and format of every view column a page shows; a page overrides only what differs.
COLUMNS = {
    "TicketId": "Ticket",
    "CircuitId": "Circuit",
    "CustomerName": "Customer",
    "AccountManager": "Account manager",
    "PriorityCode": "Priority",
    "IncidentClass": "Class",
    "RootCause": "Root cause",
    "OpenedAt": st.column_config.DatetimeColumn("Opened", format=_DATETIME),
    "RestoredAt": st.column_config.DatetimeColumn("Restored", format=_DATETIME),
    "LastOpenedAt": st.column_config.DatetimeColumn("Last incident opened", format=_DATETIME),
    "SlaTargetHours": st.column_config.NumberColumn("Target (h)", format="%.0f"),
    "RestoreHours": st.column_config.NumberColumn("Restore (h)", format="%.1f"),
    "HoursOverTarget": st.column_config.NumberColumn("Over target (h)", format="%.1f"),
    "IsSlaMet": st.column_config.CheckboxColumn("SLA met"),
    "IsRepeat": st.column_config.CheckboxColumn("Repeat"),
    "TicketsInWindow": st.column_config.NumberColumn("Tickets in window", format="%d"),
    "AgeDays": st.column_config.NumberColumn("Days open", format="%d"),
    "ActionId": "Action",
    "ActionType": "Type",
    "StartDate": st.column_config.DateColumn("Start", format="DD MMM YYYY"),
    "CompletionDate": st.column_config.DateColumn("Completed", format="DD MMM YYYY"),
    "IncidentsBefore": st.column_config.NumberColumn("Before", format="%d"),
    "IncidentsAfter": st.column_config.NumberColumn("After", format="%d"),
    "ControlCircuits": st.column_config.NumberColumn("Controls", format="%d"),
    "ControlBefore": st.column_config.NumberColumn("Control before", format="%.2f", help=_AVG_CONTROL),
    "ControlAfter": st.column_config.NumberColumn("Control after", format="%.2f", help=_AVG_CONTROL),
    "CheckCode": "Check",
    "CheckType": "Type",
    "CheckName": "Check name",
    "AffectedRows": st.column_config.NumberColumn("Affected rows", format="%d"),
    "UnhandledRows": st.column_config.NumberColumn("Unhandled rows", format="%d"),
    "ParameterCode": "Parameter",
    "ParameterValue": "Value",
}


def table(df: pd.DataFrame, **overrides) -> None:
    """Short tables show every row without a scroll bar; long lists scroll inside a fixed height."""
    height = min(35 * (len(df) + 1) + 3, 423)
    column_config = {c: COLUMNS[c] for c in df.columns if c in COLUMNS} | overrides
    st.dataframe(df, hide_index=True, width="stretch", height=height, column_config=column_config)
