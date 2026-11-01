# Technical Walkthrough

> **SIMULATED SCENARIO.** NorthGrid Telecom and its data are fictional.

A short guided tour for a BI developer reviewing the project. Decisions and trade-offs in detail:
`TECHNICAL_DECISIONS.md`.

## 1. How the solution was designed

1. Read the requirements (`docs/01-business-requirements.md`) and the source handover note.
2. Profiled the source: 18,889 tickets, with 369 marked duplicates, 549 cancelled, 30 restored before opened,
   33 on unknown circuits and 76 circuits without a region.
3. Fixed the split of work: rules in SQL, ratios and time logic in DAX, ingestion and types in Power Query.
4. Built and ran the SQL layer, then the TMDL model, then the report with the `pbir` CLI.
5. Opened the report in Power BI Desktop, validated every main KPI against independent SQL (21 of 21 match),
   reviewed every page on screen and fixed what the screenshots showed.

## 2. What is calculated in SQL

| Logic | Object |
|---|---|
| Ticket classification (valid, duplicate, cancelled), `DPC` root cause | `dw.usp_Refresh` → `dw.FactIncident.IncidentClass`, `IsCounted` |
| Restoration hours, SLA target, in scope, met (exact seconds) | `RestoreHours`, `SlaTargetHours`, `IsSlaInScope`, `IsSlaMet` |
| Repeat flag (another ticket restored in the window before opening) | `IsRepeat` |
| Daily backlog with age and bucket | `dw.FactBacklogDaily` |
| Daily chronic circuits | `dw.FactChronicDaily` |
| Before/after incidents per action and the matched control group | `dw.FactActionEffect` |
| Data quality checks | `dq.usp_RunChecks`, `dq.vw_UnmarkedOverlap` |

## 3. What is calculated in DAX

- Sums and ratios of the SQL components: `Incidents`, `MTTR (h)`, `SLA Compliance %`, `Repeat Rate %`.
- `Active Circuits` at the end of any period (from the circuit dimension, so it responds to region,
  technology and tier).
- Snapshot reading for backlog and chronic counts (`MAX('Date'[Date])`).
- Restored-date logic with `USERELATIONSHIP`.
- Comparisons with the previous month and last year, and 13-month trends, through two calculation groups.
- Report helpers: header text with the data date and the active filters.

## 4. How the model is organized

- Star schema: `Incident`, `Backlog Snapshot`, `Chronic Snapshot`, `Improvement Action` (facts);
  `Date`, `Circuit`, `Priority`, `Root Cause`, `Age Bucket`, `Action Type` (dimensions).
- All measures in `_Measures`, in numbered display folders, each with a description.
- Keys and 1/0 flags hidden; business names in the model, SQL names in the views.
- Support tables without relationships: `KPI Parameter`, `Data Quality Check`, `Processing Status`,
  `Trend Month`.

## 5. Performance choices

- Expensive window logic runs once per processing run, not on refresh or at query time.
- Temporary tables with clustered and filtered indexes inside the procedure (the repeat lookup index measured
  about 10% faster at this volume).
- Change detection skips unchanged runs (about 10 ms instead of 4.7 s).
- Import model of 1.6 MB, integer keys, no calculated columns, measures as `SUM`/`DIVIDE`; all Power Query
  steps fold.

## 6. Techniques worth a look

| Technique | Where |
|---|---|
| Matched control group to expose regression to the mean | `dw.usp_Refresh`, section K9; Improvement Actions page |
| Calculation group with `ISSELECTEDMEASURE` and a dynamic format string (relative % vs percentage points) | `Time Comparison.tmdl` |
| Disconnected axis + calculation group for a trend that ends at the selected month | `Trend Month.tmdl`, `Trend Window.tmdl` |
| Inferred dimension members for orphan facts | `DimCircuit.IsInferred` |
| Idempotent job: checksum fingerprint, `sp_getapplock`, single transaction, run log | `dw.usp_Refresh`, `dw.RefreshLog` |
| "Handled" vs "broken" data quality checks | `dq.usp_RunChecks` |
| Validation by independent re-implementation, run against the live Desktop engine | `validation/` |
| TMDL validated with the TOM shipped in Power BI Desktop | `powerbi/validate_model.ps1` |

## 7. What to inspect first

1. **Report, Overview page**: the scorecard (Time Comparison) and the 13-month trends; change the Month filter
   in the filter pane and watch both react.
2. **Improvement Actions page**: the requested before/after (−84.6%) next to the control group (−83.3%).
3. **`database/05_dw_refresh.sql`**: all business rules in one procedure.
4. **`powerbi/NorthGridOps.SemanticModel/definition/tables/_Measures.tmdl`**: 34 short KPI measures, plus 21 that only the design variants use (folder 8. Design Support).
5. **`validation/run_validation.ps1`**: run it with the report open to reproduce the 21 checks.
6. **`docs/05-validation-results.md`**: what was checked, what was found, what is still open.
