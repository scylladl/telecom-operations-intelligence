"""KPI calculations on the rpt views.

The rules are the ones the Power BI measures apply (docs/04-kpi-dictionary.md). SQL already delivers
1/0 components per ticket or snapshot, so this module only filters, sums and divides: every rate is
summed for the slice before dividing, never averaged from sub-totals.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

OVER_30_DAYS = 5  # AgeBucketCode of the "more than 30 days" bucket

# name: (lower is better, change vs a prior period: "relative" or "pp")
KPI_POLARITY = {
    "Incidents": (True, "relative"),
    "Incidents per 100 Circuits": (True, "relative"),
    "MTTR (h)": (True, "relative"),
    "SLA Compliance %": (False, "pp"),
    "Repeat Rate %": (True, "pp"),
}


@dataclass(frozen=True)
class Filters:
    """The report-level filters of the Power BI report: one month plus optional circuit and priority slices."""
    month: int  # yyyymm
    regions: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    tiers: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()


def prepare(views: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Typed copies of the views, with month keys and circuit attributes joined onto each fact."""
    date = views["date"].assign(MonthKey=lambda x: x["DateKey"] // 100)
    months = (
        date.groupby("MonthKey")
        .agg(MonthLabel=("MonthLabel", "first"), MonthEnd=("Date", "max"))
        .assign(MonthEnd=lambda x: pd.to_datetime(x["MonthEnd"]))
    )
    months["MonthEndKey"] = months["MonthEnd"].dt.strftime("%Y%m%d").astype(int)

    circuit = views["circuit"].assign(
        InstallDate=lambda x: pd.to_datetime(x["InstallDate"]),
        DecommissionDate=lambda x: pd.to_datetime(x["DecommissionDate"]),
    )
    attributes = circuit[["CircuitKey", "CircuitId", "CustomerName", "Region", "Technology", "Tier", "TierSort",
                          "AccountManager"]]

    # pyodbc returns SQL decimals as Python Decimal objects
    incident = views["incident"].astype(
        {"RestoreHours": float, "SlaTargetHours": float, "HoursOverTarget": float}
    ).merge(attributes, on="CircuitKey").merge(views["root_cause"][["RootCauseCode", "RootCause"]], on="RootCauseCode")
    incident["OpenedMonth"] = incident["OpenedDateKey"] // 100
    incident["RestoredMonth"] = (incident["RestoredDateKey"] // 100).astype("Int64")
    incident["IsDuplicate"] = incident["IncidentClass"] == "Duplicate"
    incident["IsCancelled"] = incident["IncidentClass"] == "Cancelled"

    backlog = views["backlog"].merge(attributes, on="CircuitKey").merge(views["age_bucket"], on="AgeBucketCode")
    chronic = views["chronic"].merge(attributes, on="CircuitKey")
    action = views["action"].astype({"ControlBefore": float, "ControlAfter": float}).merge(
        attributes, on="CircuitKey").merge(views["action_type"], on="ActionTypeCode")

    return {
        "months": months,
        "circuit": circuit,
        "priority": views["priority"],
        "root_cause": views["root_cause"],
        "age_bucket": views["age_bucket"],
        "incident": incident,
        "backlog": backlog,
        "chronic": chronic,
        "action": action,
        "kpi_parameter": views["kpi_parameter"],
        "dq_check": views["dq_check"],
        "status": views["status"],
    }


def shift_month(month: int, offset: int) -> int:
    year, month_index = divmod((month // 100) * 12 + month % 100 - 1 + offset, 12)
    return year * 100 + month_index + 1


def scope(df: pd.DataFrame, f: Filters, by_priority: bool = True) -> pd.DataFrame:
    """Rows inside the circuit and priority slices. Chronic circuits, active circuits and actions
    have no priority, so the priority filter does not reach them (same as the model relationships)."""
    mask = pd.Series(True, index=df.index)
    for column, values in (("Region", f.regions), ("Technology", f.technologies), ("Tier", f.tiers)):
        if values:
            mask &= df[column].isin(values)
    if by_priority and f.priorities:
        mask &= df["PriorityCode"].isin(f.priorities)
    return df[mask]


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.where(denominator != 0)


def add_rates(t: pd.DataFrame) -> pd.DataFrame:
    """Rates from summed components; a zero denominator gives NaN, like DIVIDE returns BLANK."""
    if "SlaInScope" in t:
        t["SLA Breaches"] = t["SlaInScope"] - t["SlaMet"]
        t["SLA Compliance %"] = _ratio(t["SlaMet"], t["SlaInScope"])
    if "RestoredTickets" in t:
        t["MTTR (h)"] = _ratio(t["RestorationHours"], t["RestoredTickets"])
    if "RepeatIncidents" in t:
        t["Repeat Rate %"] = _ratio(t["RepeatIncidents"], t["Incidents"])
    return t


RESTORED_COMPONENTS = {"RestoredTickets": ("IsRestored", "sum"), "RestorationHours": ("RestoreHours", "sum"),
                       "SlaInScope": ("IsSlaInScope", "sum"), "SlaMet": ("IsSlaMet", "sum")}
OPENED_COMPONENTS = {"Incidents": ("IsCounted", "sum"), "RepeatIncidents": ("IsRepeat", "sum")}


def monthly(d: dict, f: Filters) -> pd.DataFrame:
    """One row per month with every headline KPI. Counts use the opened date, restoration KPIs the restored
    date, and the backlog, chronic and active-circuit snapshots the last day of the month."""
    months = d["months"]
    incident = scope(d["incident"], f)

    opened = incident.groupby("OpenedMonth").agg(
        **OPENED_COMPONENTS,
        Duplicates=("IsDuplicate", "sum"),
        Cancelled=("IsCancelled", "sum"),
    )
    restored = incident.dropna(subset=["RestoredMonth"]).groupby("RestoredMonth").agg(**RESTORED_COMPONENTS)

    backlog = scope(d["backlog"], f)
    backlog = backlog[backlog["SnapshotDateKey"].isin(months["MonthEndKey"])]
    backlog = backlog.assign(Over30=backlog["AgeBucketCode"] == OVER_30_DAYS).groupby(
        backlog["SnapshotDateKey"] // 100
    ).agg(OpenBacklog=("TicketId", "size"), Over30=("Over30", "sum"), OldestDays=("AgeDays", "max"))

    chronic = scope(d["chronic"], f, by_priority=False)
    chronic = chronic[chronic["SnapshotDateKey"].isin(months["MonthEndKey"])].groupby(
        chronic["SnapshotDateKey"] // 100
    ).size().rename("Chronic Circuits")

    circuits = scope(d["circuit"], f, by_priority=False)
    circuits = circuits[~circuits["IsInferred"].astype(bool)]
    in_service = circuits["DecommissionDate"].isna()
    active = pd.Series(
        [((circuits["InstallDate"] <= end) & (in_service | (circuits["DecommissionDate"] > end))).sum()
         for end in months["MonthEnd"]],
        index=months.index, name="Active Circuits",
    )

    t = months.join([opened, restored, backlog, chronic, active])
    counts = ["Incidents", "RepeatIncidents", "Duplicates", "Cancelled", "RestoredTickets", "RestorationHours",
              "SlaInScope", "SlaMet", "OpenBacklog", "Over30", "Chronic Circuits"]
    t[counts] = t[counts].fillna(0)
    t = add_rates(t)
    t["Incidents per 100 Circuits"] = _ratio(t["Incidents"], t["Active Circuits"]) * 100
    t["Backlog Over 30 Days %"] = _ratio(t["Over30"], t["OpenBacklog"])
    t["Duplicate Share %"] = _ratio(t["Duplicates"], t["Duplicates"] + t["Incidents"])
    return t


def change(current: float, previous: float, kind: str) -> float:
    """Change vs a prior period: relative for counts and hours, percentage points for rates."""
    if pd.isna(current) or pd.isna(previous):
        return np.nan
    if kind == "pp":
        return (current - previous) * 100
    return (current - previous) / previous if previous else np.nan


def last_months(table: pd.DataFrame, month: int, count: int = 13) -> pd.DataFrame:
    """The trend window: the selected month and the months before it."""
    return table.loc[:month].tail(count)


def opened_in(d: dict, f: Filters) -> pd.DataFrame:
    incident = scope(d["incident"], f)
    return incident[incident["OpenedMonth"] == f.month]


def restored_in(d: dict, f: Filters) -> pd.DataFrame:
    incident = scope(d["incident"], f)
    return incident[incident["RestoredMonth"] == f.month]


def restoration_by(d: dict, f: Filters, dims: list[str]) -> pd.DataFrame:
    return add_rates(restored_in(d, f).groupby(dims).agg(**RESTORED_COMPONENTS)).reset_index()


def repeat_by(d: dict, f: Filters, dims: list[str]) -> pd.DataFrame:
    return add_rates(opened_in(d, f).groupby(dims).agg(**OPENED_COMPONENTS)).reset_index()


def snapshot(df: pd.DataFrame, d: dict, f: Filters) -> pd.DataFrame:
    """Rows of a daily snapshot table on the last day of the selected month."""
    return df[df["SnapshotDateKey"] == d["months"].loc[f.month, "MonthEndKey"]]


def worst_breaches(d: dict, f: Filters, top: int = 10) -> pd.DataFrame:
    breaches = restored_in(d, f)
    return breaches[breaches["HoursOverTarget"] > 0].nlargest(top, "HoursOverTarget")


def circuit_history(d: dict, circuit_id: str) -> pd.DataFrame:
    """Every ticket of one circuit, cancelled and duplicates included (the Circuit Detail drill-through)."""
    incident = d["incident"]
    return incident[incident["CircuitId"] == circuit_id].sort_values("OpenedAt", ascending=False)


def circuit_totals(d: dict, circuit_id: str) -> pd.Series:
    """KPI components of one circuit over all months; the backlog is the one open at the data date."""
    history = circuit_history(d, circuit_id)
    totals = pd.Series({name: history[column].sum()
                        for name, (column, _) in {**OPENED_COMPONENTS, **RESTORED_COMPONENTS}.items()})
    backlog = d["backlog"]
    totals["OpenBacklog"] = ((backlog["CircuitId"] == circuit_id)
                             & (backlog["SnapshotDateKey"] == d["months"]["MonthEndKey"].max())).sum()
    return totals


def action_effect(actions: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """K9 by group. Change % is the before/after comparison the client asked for; the matched rows compare
    treated circuits with untreated circuits that had the same incidents before (regression to the mean).
    Not filtered by the month: each action has its own fixed windows."""
    matched = actions["HasControl"].astype(bool)
    parts = pd.DataFrame({
        "Actions Evaluated": actions["IsEvaluable"].astype(int),
        "Before": actions["IncidentsBefore"].fillna(0),
        "After": actions["IncidentsAfter"].fillna(0),
        "Matched Actions": matched.astype(int),
        "TreatedBefore": actions["IncidentsBefore"].fillna(0).where(matched, 0),
        "TreatedAfter": actions["IncidentsAfter"].fillna(0).where(matched, 0),
        "ControlBefore": actions["ControlBefore"].fillna(0).where(matched, 0),
        "ControlAfter": actions["ControlAfter"].fillna(0).where(matched, 0),
    })
    t = parts.groupby([actions[c] for c in by]).sum() if by else parts.sum().to_frame().T
    t["Incident Change %"] = _ratio(t["After"] - t["Before"], t["Before"])
    t["Treated Change % (Matched)"] = _ratio(t["TreatedAfter"] - t["TreatedBefore"], t["TreatedBefore"])
    t["Control Change %"] = _ratio(t["ControlAfter"] - t["ControlBefore"], t["ControlBefore"])
    t["Net Action Effect (pp)"] = (t["Treated Change % (Matched)"] - t["Control Change %"]) * 100
    return t.reset_index() if by else t
