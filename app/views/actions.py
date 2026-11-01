import plotly.graph_objects as go
import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]
actions = kpis.scope(d["action"], f, by_priority=False)
total = kpis.action_effect(actions).iloc[0]

headline = (
    f"Circuits with an action had {abs(total['Treated Change % (Matched)']):.0%} fewer incidents afterwards, but "
    f"comparable untreated circuits also fell {abs(total['Control Change %']):.0%}. "
    f"Net effect of the actions: {ui.fmt(total['Net Action Effect (pp)'], 'pp')}."
)
ui.header("Improvement Actions", d, f, headline)
window = d["kpi_parameter"].set_index("ParameterCode").loc["ACTION_EFFECT_WINDOW_DAYS", "ParameterValue"]
st.caption(f"Each completed action is measured over its own windows ({window:.0f} days before the start, "
           f"{window:.0f} days after the completion), so the month filter does not apply here. Actions target circuits that just failed "
           "several times, and those circuits improve anyway; the matched control group shows how much.")

evaluated, naive, control, net = st.columns(4)
ui.metric(evaluated, "Actions evaluated", total["Actions Evaluated"], "int")
ui.metric(naive, "Incident change (before vs after)", total["Incident Change %"], "signed_pct")
ui.metric(control, "Control group change", total["Control Change %"], "signed_pct")
ui.metric(net, "Net action effect", total["Net Action Effect (pp)"], "pp")

left, right = st.columns(2)
with left:
    by_type = kpis.action_effect(actions, ["ActionType"]).sort_values("Net Action Effect (pp)")
    fig = go.Figure([
        go.Bar(y=by_type["ActionType"], x=by_type[column], name=label, orientation="h",
               marker={"color": color, "cornerradius": 4},
               text=[ui.fmt(v, "signed_pct") for v in by_type[column]], textposition="inside",
               insidetextanchor="start", textfont={"color": "white"},
               hovertemplate=f"%{{y}} · {label}: %{{text}}<extra></extra>")
        for column, label, color in (("Treated Change % (Matched)", "Treated circuits", ui.CATEGORICAL[0]),
                                     ("Control Change %", "Comparable untreated circuits", ui.CATEGORICAL[1]))
    ])
    fig.update_layout(barmode="group")
    fig = ui.style(fig, "Incident change after the action vs comparable circuits", height=360)
    fig.update_xaxes(tickformat=".0%")
    ui.show(fig)
with right:
    by_region = kpis.action_effect(actions, ["Region"]).dropna(subset=["Net Action Effect (pp)"])
    by_region = by_region.sort_values("Net Action Effect (pp)", ascending=False)
    # negative is good here: the action removed incidents beyond the natural decline
    colors = [ui.SERIES if v < 0 else ui.CRITICAL for v in by_region["Net Action Effect (pp)"]]
    fig = go.Figure(go.Bar(
        y=by_region["Region"], x=by_region["Net Action Effect (pp)"], orientation="h",
        marker={"color": colors, "cornerradius": 4},
        text=[ui.fmt(v, "pp") for v in by_region["Net Action Effect (pp)"]], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig = ui.style(fig, "Net action effect (pp) by region, negative = fewer incidents", height=360)
    spread = by_region["Net Action Effect (pp)"].abs().max() * 1.35  # room for the labels on both sides
    fig.update_xaxes(zeroline=True, zerolinecolor=ui.MUTED, range=[-spread, spread])
    ui.show(fig)

st.subheader("Evaluated improvement actions")
ui.table(
    actions[actions["EvaluationStatus"] == "Evaluated"].sort_values("ActionId", ascending=False)[
        ["ActionId", "ActionType", "CircuitId", "Region", "StartDate", "CompletionDate",
         "IncidentsBefore", "IncidentsAfter", "ControlCircuits", "ControlBefore", "ControlAfter"]],
    ActionId="Action", ActionType="Type", CircuitId="Circuit",
    StartDate=st.column_config.DateColumn("Start", format="DD MMM YYYY"),
    CompletionDate=st.column_config.DateColumn("Completed", format="DD MMM YYYY"),
    IncidentsBefore=st.column_config.NumberColumn("Before", format="%d"),
    IncidentsAfter=st.column_config.NumberColumn("After", format="%d"),
    ControlCircuits=st.column_config.NumberColumn("Controls", format="%d"),
    ControlBefore=st.column_config.NumberColumn("Control before", format="%.2f",
                                                help="Average incidents per control circuit"),
    ControlAfter=st.column_config.NumberColumn("Control after", format="%.2f",
                                               help="Average incidents per control circuit"),
)
