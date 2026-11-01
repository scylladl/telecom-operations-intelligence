import streamlit as st

import kpis
import narrative
import ui

d = ui.load_data()
f = st.session_state["filters"]
actions = kpis.scope(d["action"], f, by_priority=False)
total = kpis.action_effect(actions).iloc[0]

ui.header("Improvement Actions", d, f, narrative.actions(total))
st.caption(narrative.action_window(d))

evaluated, naive, control, net = st.columns(4)
ui.metric(evaluated, "Actions evaluated", total["Actions Evaluated"], "int")
ui.metric(naive, "Incident change (before vs after)", total["Incident Change %"], "signed_pct")
ui.metric(control, "Control group change", total["Control Change %"], "signed_pct")
ui.metric(net, "Net action effect", total["Net Action Effect (pp)"], "pp")

left, right = st.columns(2)
with left:
    ui.treated_vs_control(kpis.action_effect(actions, ["ActionType"]))
with right:
    ui.net_effect_by(kpis.action_effect(actions, ["Region"]), "Region")

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
