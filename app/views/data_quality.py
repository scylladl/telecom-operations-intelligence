import streamlit as st

import kpis
import ui

d = ui.load_data()
f = st.session_state["filters"]
t = kpis.monthly(d, f)
month = t.loc[f.month]
checks = d["dq_check"]
failed = int((checks["Result"] == "Fail").sum())

headline = (
    f"{ui.month_label(d, f.month)}: {ui.fmt(month['Duplicates'], 'int')} duplicate tickets "
    f"({ui.fmt(month['Duplicate Share %'], 'pct')}), excluded from every KPI. "
    + ("All data quality checks pass." if failed == 0 else f"{failed} checks failing.")
)
ui.header("Data Quality", d, f, headline)

duplicates, share, cancelled, failing = st.columns(4)
ui.metric(duplicates, "Duplicate tickets", month["Duplicates"], "int")
ui.metric(share, "Duplicate share", month["Duplicate Share %"], "pct")
ui.metric(cancelled, "Cancelled tickets", month["Cancelled"], "int")
ui.metric(failing, "Failed checks", failed, "int")

ui.trend(t, f, "Duplicates", "Duplicate tickets (DPC) by month, last 13 months", "int", bars=True)

st.subheader("Data quality checks (dq.usp_RunChecks)")
ui.table(checks[["CheckCode", "CheckType", "CheckName", "Result", "AffectedRows", "UnhandledRows", "Handling"]],
         CheckCode="Check", CheckType="Type", CheckName="Check name",
         AffectedRows=st.column_config.NumberColumn("Affected rows", format="%d"),
         UnhandledRows=st.column_config.NumberColumn("Unhandled rows", format="%d"))

st.subheader("KPI parameters used by the last processing run")
ui.table(d["kpi_parameter"], ParameterCode="Parameter", ParameterValue="Value")
