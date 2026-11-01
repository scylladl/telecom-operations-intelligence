"""Shared page parts: data loading, the report filters, page header, KPI cards and chart styling."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db
import kpis

# Reference palette of the dataviz method (validated for colour vision deficiency, adjacent pairs).
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SERIES = CATEGORICAL[0]
CONTEXT = "#c3c2b7"
ORDINAL = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"]  # age buckets up to 30 days
CRITICAL = "#d03b3b"  # alert colour, only for the more-than-30-days bucket (project rule)
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e1e0d9"


@st.cache_resource
def _engine():
    return db.create_engine()


# The data changes once a day (database/refresh.ps1); a 15-minute cache keeps pages fast and still
# picks up a new processing run without restarting the app.
@st.cache_data(ttl=900, show_spinner="Loading data from SQL Server...")
def load_data() -> dict:
    return kpis.prepare(db.read_views(_engine()))


def sidebar_filters(d: dict) -> kpis.Filters:
    """The five report-level filters of the Power BI report, shared by every page."""
    months = d["months"]
    circuit = d["circuit"]
    with st.sidebar:
        month = st.selectbox("Month", months.index[::-1], format_func=lambda m: months.loc[m, "MonthLabel"],
                             key="month")
        regions = st.multiselect("Region", sorted(circuit["Region"].unique()), key="regions")
        technologies = st.multiselect("Technology", sorted(circuit["Technology"].unique()), key="technologies")
        tiers = st.multiselect("Tier", circuit.drop_duplicates("Tier").sort_values("TierSort")["Tier"], key="tiers")
        priorities = st.multiselect("Priority", d["priority"].sort_values("SortOrder")["PriorityCode"],
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
        title={"text": title, "font": {"size": 15, "color": INK}, "x": 0, "xanchor": "left"},
        height=height, margin={"l": 8, "r": 8, "t": 48, "b": 8},
        font={"family": 'system-ui, -apple-system, "Segoe UI", sans-serif', "size": 12, "color": MUTED},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={"bgcolor": "white", "font_color": INK},
        legend={"orientation": "h", "yanchor": "top", "y": -0.08, "x": 0, "title": None, "traceorder": "normal"},
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, linecolor=CONTEXT, ticks="", title=None, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=CONTEXT, title=None, automargin=True,
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
        colors = [SERIES if m == f.month else CONTEXT for m in window.index]
        fig = go.Figure(go.Bar(x=labels, y=window[column], marker={"color": colors, "cornerradius": 4},
                               hovertemplate=f"%{{x}}: {text_format}<extra></extra>"))
    else:
        fig = go.Figure(go.Scatter(x=labels, y=window[column], mode="lines+markers",
                                   line={"color": SERIES, "width": 2}, marker={"size": 8, "color": SERIES},
                                   hovertemplate=f"%{{x}}: {text_format}<extra></extra>"))
    last = window.iloc[-1]
    fig.add_annotation(x=last["MonthLabel"], y=last[column], text=fmt(last[column], kind), showarrow=False,
                       yshift=14, font={"color": INK, "size": 12})
    fig = style(fig, title, percent_axis=kind == "pct")
    fig.update_xaxes(tickangle=0, nticks=7)
    show(fig)


def ranked_bars(df: pd.DataFrame, category: str, value: str, title: str, kind: str, lowest_first: bool) -> None:
    """Horizontal bars, the category to look at first on top; every bar carries its value."""
    # plotly draws the first row at the bottom
    df = df.dropna(subset=[value]).sort_values(value, ascending=not lowest_first)
    fig = go.Figure(go.Bar(y=df[category], x=df[value], orientation="h", marker={"color": SERIES, "cornerradius": 4},
                           text=[fmt(v, kind) for v in df[value]], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{text}<extra></extra>"))
    fig = style(fig, title, height=max(220, 60 + 34 * len(df)))
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, df[value].max() * 1.15])  # room for labels
    fig.update_yaxes(showgrid=False)
    show(fig)


def table(df: pd.DataFrame, **column_config) -> None:
    """Short tables show every row without a scroll bar; long lists scroll inside a fixed height."""
    height = min(35 * (len(df) + 1) + 3, 423)
    st.dataframe(df, hide_index=True, width="stretch", height=height, column_config=column_config)
