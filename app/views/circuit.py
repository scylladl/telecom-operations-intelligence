import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]

# Default to the circuit with most tickets in the chronic window at the end of the selected month.
chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
circuit_ids = d["circuit"]["CircuitId"].sort_values().tolist()
default = chronic.nlargest(1, "TicketsInWindow")["CircuitId"].iloc[0] if not chronic.empty else circuit_ids[0]

ui.header("Circuit Detail", d, None)
circuit_id = st.selectbox("Circuit", circuit_ids, index=circuit_ids.index(default))
st.caption("All months of the circuit's history; the sidebar filters do not apply on this page.")

circuit = d["circuit"].set_index("CircuitId").loc[circuit_id]
st.markdown(
    f"**{circuit['CustomerName']}** · {circuit['Segment']} · {circuit['Tier']} tier · {circuit['Technology']} · "
    f"{circuit['Region']} ({circuit['Province']}) · account manager {circuit['AccountManager']}"
)

totals = kpis.add_rates(kpis.circuit_totals(d, circuit_id).to_frame().T).iloc[0]
incidents, mttr, repeat = st.columns(3)
ui.metric(incidents, "Incidents", totals["Incidents"], "int")
ui.metric(mttr, "MTTR (h)", totals["MTTR (h)"], "dec1")
ui.metric(repeat, "Repeat Rate %", totals["Repeat Rate %"], "pct")

st.subheader("Incident history (all tickets, including cancelled and duplicates)")
ui.table(
    kpis.circuit_history(d, circuit_id)[["TicketId", "IncidentClass", "PriorityCode", "RootCause", "OpenedAt",
                                         "RestoredAt", "RestoreHours", "SlaTargetHours", "IsSlaMet", "IsRepeat"]],
    TicketId="Ticket", IncidentClass="Class", PriorityCode="Priority", RootCause="Root cause",
    OpenedAt=st.column_config.DatetimeColumn("Opened", format="DD MMM YYYY HH:mm"),
    RestoredAt=st.column_config.DatetimeColumn("Restored", format="DD MMM YYYY HH:mm"),
    RestoreHours=st.column_config.NumberColumn("Restore (h)", format="%.1f"),
    SlaTargetHours=st.column_config.NumberColumn("Target (h)", format="%.0f"),
    IsSlaMet=st.column_config.CheckboxColumn("SLA met"),
    IsRepeat=st.column_config.CheckboxColumn("Repeat"),
)
