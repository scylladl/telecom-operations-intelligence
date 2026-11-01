# KPI Dictionary

> **SIMULATED SCENARIO.** NorthGrid Telecom, its data and every value shown in the report are fictional.

Business rules come from `docs/01-business-requirements.md`, section 7, and change request CR-001.
Owner of every KPI: Head of B2B Service Assurance (fictional). Windows marked *parameter* are read from
`cfg.KpiParameter` at every processing run.

## Rules shared by every KPI

| Rule | Implementation |
|---|---|
| Cancelled tickets never count | `IncidentClass = 'Cancelled'` → `IsCounted = 0` (`dw.usp_Refresh`) |
| Duplicate tickets never count; only the original counts | Marked duplicate whose original was still open → `IncidentClass = 'Duplicate'`, root cause `DPC`, `IsCounted = 0`. Opened after the original was closed → a new failure, counted |
| Counts use the opened date | Active relationship `Incident[Opened Date Key] → Date` |
| Restoration KPIs use the restored date | Inactive relationship `Incident[Restored Date Key] → Date`, activated with `USERELATIONSHIP` in the measures |
| Restoration time in calendar hours | `DATEDIFF(second, OpenedAt, RestoredAt) / 3600` |
| Customer-premises causes are excluded from SLA only | `ref.RootCause.IsCustomerAttributable = 1` → `IsSlaInScope = 0` |
| Tickets restored before they were opened (source defect) | Counted in volume and repeat; excluded from MTTR, SLA and backlog |
| Tickets on circuits missing from the inventory (source defect) | Inferred circuit with Unknown region, technology and tier; counted in volume; no SLA target, so outside SLA |

## KPIs

| # | KPI | Definition | SQL (prepared per ticket or snapshot) | DAX measure | Grain / period |
|---|---|---|---|---|---|
| K1 | Incident volume | Valid tickets opened | `FactIncident.IsCounted` (1/0) | `Incidents = SUM ( 'Incident'[Is Counted] )` | Day, month; any dimension |
| K2 | Incidents per 100 circuits | K1 ÷ circuits active at the end of the period × 100 | `DimCircuit.InstallDate`, `DecommissionDate`, `IsInferred` | `Active Circuits` (circuits installed on or before the last date in context and not decommissioned by then), `Incidents per 100 Circuits` | Month |
| K3 | MTTR (h) | Average of restored − opened, restored tickets | `IsRestored` (1/0), `RestoreHours` | `MTTR (h) = DIVIDE ( [Restoration Hours], [Restored Tickets] )`, both through `USERELATIONSHIP` | Month, by restored date |
| K4 | SLA compliance % | Restored tickets within the tier and priority target ÷ restored tickets in scope | `IsSlaInScope`, `IsSlaMet` (compared in exact seconds), `SlaTargetHours` from `ref.SlaTarget` | `SLA Compliance % = DIVIDE ( [SLA Met Tickets], [SLA In-Scope Tickets] )` | Month, by restored date |
| K5 | Repeat incident rate % | Tickets whose circuit had another valid ticket **restored** in the 30 days (*parameter*) before this one opened ÷ all tickets | `IsRepeat` (1/0), computed with an `EXISTS` lookup | `Repeat Rate % = DIVIDE ( [Repeat Incidents], [Incidents] )` | Month, by opened date |
| K6 | Chronic circuits | Circuits with 3 or more (*parameter*) valid tickets opened in the last 60 days (*parameter*), at the end of each day | `dw.FactChronicDaily`: one row per chronic circuit per day | `Chronic Circuits`: rows on the last date in context | Day snapshot, shown at the end of the selected month |
| K7 | Open backlog | Valid tickets opened and not restored at the end of the day | `dw.FactBacklogDaily`: one row per open ticket per day | `Open Backlog`: rows on the last date in context | Day snapshot |
| K8 | Backlog aging | K7 by days open: 0–2, 3–7, 8–15, 16–30, more than 30 | `FactBacklogDaily.AgeDays`, `AgeBucketCode` | `Open Backlog` by `Age Bucket`; `Backlog Over 30 Days %` | Day snapshot |
| K9 | Action effectiveness | Completed actions: valid incidents in the 90 days (*parameter*) before the start vs the 90 days after the completion; only actions with full windows inside the data | `dw.FactActionEffect`: `IncidentsBefore`, `IncidentsAfter`, plus a matched control group | `Incident Change %` (as requested), `Treated Change % (Matched)`, `Control Change %`, `Net Action Effect (pp)` | Per action; aggregated by type and region. Not filtered by the report month |

### Why ratios are correct under any filter

The SQL layer delivers **components** per ticket (1/0 flags and hours), never pre-computed percentages.
Every rate is `DIVIDE ( SUM ( numerator ), SUM ( denominator ) )` evaluated in the filter context, so the SLA
of "South + Fixed Wireless + March" is computed from that slice's tickets, not averaged from regional rates.
This was the client's first condition when the approach was accepted.

### K9: the comparison the client asked for, and the one to read

The requested before/after comparison shows a large drop (−84.6% over 413 evaluated actions, simulated).
Actions are chosen for circuits that just had several incidents, and such circuits improve anyway
(regression to the mean). The control group makes this visible: untreated circuits of the same technology
with the **same** number of incidents in the same before window, measured over the same dates.
They dropped −83.3%. The net effect, −1.1 percentage points overall, is what the actions added
(values from the simulated data; matched actions only: 251 of 413).

## Supporting measures

| Measure | Purpose |
|---|---|
| `SLA Breaches`, `Max Hours Over Target` | Worst-breach list (top 10 by hours over target) |
| `Tickets In Chronic Window`, `Last Incident Opened` | Chronic circuit list |
| `Average Backlog`, `Backlog Age (days)` | Backlog context; oldest open tickets |
| `Duplicate Tickets`, `Duplicate Share %`, `Cancelled Tickets`, `Failed Checks` | Data quality page (CR-001 condition 2) |
| `Data Status`, `Filter Context` | Header of every page: data date, processing time, active filters (FR-09) |

## Design support measures (folder *8. Design Support*)

Used by the design variants only; same definitions as above, no new business rules.

| Measures | Purpose |
|---|---|
| `<KPI> PM`, `<KPI> MoM`, `<KPI> MoM Color` for Incidents, Incidents per 100 Circuits, MTTR (h), SLA Compliance %, Repeat Rate % | Explicit prior-month value, change (relative or pp) and change colour for new-card reference labels, which cannot use a calculation group. Colour polarity: lower is better except SLA |
| `Headline Overview`, `Headline SLA`, `Headline Repeat`, `Headline Backlog`, `Headline Actions`, `Headline Data Quality` | One sentence per page built from the same measures |

## Calculation groups

| Group | Items | Used for |
|---|---|---|
| Time Comparison | Selected Month, Prior Month, MoM, Same Month LY, YoY | KPI scorecard (FR-01). MoM/YoY are relative changes for counts and hours and percentage points for rates (`ISSELECTEDMEASURE`), with a dynamic format string |
| Trend Window | Last 13 Months | 13-month trend visuals on the disconnected `Trend Month` axis, ending in the selected month |
