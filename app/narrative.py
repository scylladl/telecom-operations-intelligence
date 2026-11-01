"""One headline sentence per page, built from the KPIs (the "Headline" measures of the Power BI model)."""
import pandas as pd

import kpis
from ui import fmt, month_label


def _value(t: pd.DataFrame, name: str, month: int) -> float:
    return t[name].get(month, float("nan"))


def _parameter(d: dict, code: str) -> float:
    return d["kpi_parameter"].set_index("ParameterCode").loc[code, "ParameterValue"]


def overview(d: dict, f: kpis.Filters, t: pd.DataFrame) -> str:
    prior = kpis.shift_month(f.month, -1)
    current = {name: _value(t, name, f.month) for name in ("Incidents", "SLA Compliance %", "Repeat Rate %")}
    change = {name: kpis.change(value, _value(t, name, prior), kpis.KPI_POLARITY[name][1])
              for name, value in current.items()}
    return (
        f"{month_label(d, f.month)}: {fmt(current['Incidents'], 'int')} incidents "
        f"({fmt(change['Incidents'], 'signed_pct')} vs prior month), "
        f"SLA compliance {fmt(current['SLA Compliance %'], 'pct')} ({fmt(change['SLA Compliance %'], 'pp')}), "
        f"repeat rate {fmt(current['Repeat Rate %'], 'pct')} ({fmt(change['Repeat Rate %'], 'pp')})."
    )


def sla(d: dict, f: kpis.Filters, t: pd.DataFrame) -> str:
    month = t.loc[f.month]
    text = (f"{month_label(d, f.month)}: {fmt(month['SLA Compliance %'], 'pct')} of in-scope tickets restored within "
            f"target ({fmt(month['SLA Breaches'], 'int')} breaches).")
    by_region = kpis.restoration_by(d, f, ["Region"])
    known = by_region[by_region["Region"] != "Unknown"].dropna(subset=["SLA Compliance %"])
    if not known.empty:
        worst = known.nsmallest(1, "SLA Compliance %").iloc[0]
        text += f" Lowest region: {worst['Region']} at {fmt(worst['SLA Compliance %'], 'pct')}."
    return text


def repeat(d: dict, f: kpis.Filters, t: pd.DataFrame) -> str:
    month = t.loc[f.month]
    chronic = kpis.snapshot(kpis.scope(d["chronic"], f, by_priority=False), d, f)
    text = (f"{month_label(d, f.month)}: {fmt(month['Repeat Rate %'], 'pct')} of incidents hit a circuit restored in "
            f"the previous {_parameter(d, 'REPEAT_WINDOW_DAYS'):.0f} days. "
            f"{fmt(month['Chronic Circuits'], 'int')} circuits are chronic at month end")
    return text + (f", most of them {chronic['Technology'].mode().iloc[0]}." if not chronic.empty else ".")


def backlog(d: dict, f: kpis.Filters, t: pd.DataFrame) -> str:
    month = t.loc[f.month]
    return (f"End of {month_label(d, f.month)}: {fmt(month['OpenBacklog'], 'int')} tickets open, the oldest for "
            f"{fmt(month['OldestDays'], 'int')} days; {fmt(month['Backlog Over 30 Days %'], 'pct')} open for more "
            f"than 30 days.")


def actions(total: pd.Series) -> str:
    return (f"Circuits with an action had {abs(total['Treated Change % (Matched)']):.0%} fewer incidents afterwards, "
            f"but comparable untreated circuits also fell {abs(total['Control Change %']):.0%}. "
            f"Net effect of the actions: {fmt(total['Net Action Effect (pp)'], 'pp')}.")


def action_window(d: dict) -> str:
    window = _parameter(d, "ACTION_EFFECT_WINDOW_DAYS")
    return (f"Each completed action is measured over its own windows ({window:.0f} days before the start, "
            f"{window:.0f} days after the completion), so the month filter does not apply here. Actions target "
            "circuits that just failed several times, and those circuits improve anyway; the matched control group "
            "shows how much.")


def data_quality(d: dict, f: kpis.Filters, t: pd.DataFrame) -> str:
    month = t.loc[f.month]
    failed = int((d["dq_check"]["Result"] == "Fail").sum())
    return (f"{month_label(d, f.month)}: {fmt(month['Duplicates'], 'int')} duplicate tickets "
            f"({fmt(month['Duplicate Share %'], 'pct')}), excluded from every KPI. "
            + ("All data quality checks pass." if failed == 0 else f"{failed} checks failing."))
