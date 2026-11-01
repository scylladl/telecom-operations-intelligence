# Validation Results

> **SIMULATED SCENARIO.** All values come from synthetic data (seed 42). Measured on 2026-11-01 on the
> development laptop (SQL Server 2025 Developer, Power BI Desktop 2.159).

## Acceptance criteria

| ID | Criterion | Status | Evidence |
|---|---|---|---|
| AC-01 | One command rebuilds the database and loads the data from zero | **Passed** | `build.ps1` (deploy → generate → load → `refresh.ps1 -Force`) ran end to end in 23.8 s with all checks passing. Row counts and `CHECKSUM_AGG` of the 4 source tables and the 4 fact tables were identical before and after the rebuild, and the 21 SQL vs Power BI checks still matched |
| AC-02 | All data quality checks pass | **Passed** | 12 of 12 checks pass (table below) |
| AC-03 | K1, K3, K4, K5, K7, K9 match SQL for three cases each | **Passed** | 21 of 21 comparisons match (table below) |
| AC-04 | Changing a KPI parameter changes results without editing code | **Passed** | Repeat window 30 → 15 days, inside a rolled-back transaction: repeat incidents 3,859 → 2,375, repeat rate 21.47% → 13.22%; back to 30 days and 21.47% after the rollback |
| AC-05 | All Must requirements delivered; Should delivered or postponed | **Passed, with notes** | Requirement table below |
| AC-06 | README screenshots come from the real report after it was opened and checked | **Passed** | `docs/screenshots/` captured from Power BI Desktop with the report open (`pbir desktop screenshot`), after inspection page by page |
| AC-07 | No real company, customer, person or confidential rule | **Passed** | Fictional company, generated customers ("Client 0001"…), rules written from the public requirements; see `docs/01-business-requirements.md` |

## AC-03: SQL vs Power BI

`validation/validation_queries.sql` computes the KPIs straight from `ops`, `ref` and `cfg`, rewriting the
business rules independently of `dw.usp_Refresh`. `validation/run_validation.ps1` runs the same cases as DAX
queries against the model open in Power BI Desktop. Output saved in `validation/results.csv`.

| Test case | K1 | K3 MTTR (h) | K4 SLA % | K5 Repeat % | K7 Backlog | K9 before / after |
|---|---|---|---|---|---|---|
| Month Dec 2025 | 865 | 36.80 | 62.47% | 24.16% | 42 | 1,530 / 235 |
| Region South, Dec 2025 | 146 | 33.61 | 65.63% | 23.29% | 6 | 225 / 42 |
| Circuit NG-FWA-001453, all months | 22 | 72.16 | 66.67% | 90.91% | 0 | 10 / 8 |

Every value matches between SQL and Power BI. Tolerances: exact for counts; 0.01 h for MTTR, because the dw
layer stores hours with two decimals; 0.0001% for rates.

Discrepancies found and investigated on the way (none hidden):

| Finding | Cause | Fix |
|---|---|---|
| K7 = 0 in the independent SQL, 42 in dw | The validation query used `NOT (RestoredAt < OpenedAt)`, which is UNKNOWN when `RestoredAt` is NULL and dropped every open ticket | Validation query corrected (`RestoredAt IS NULL OR RestoredAt >= OpenedAt`) |
| Month labels in Portuguese ("dez 2025"), report filter "Dec 2025" selected nothing | `DATENAME` follows the language of the SQL login (Portuguese on this server) | `FORMAT(d, 'MMM yyyy', 'en-US')` in `dw.usp_Refresh` |
| SLA compared with hours rounded to 2 decimals | A ticket restored within 36 seconds of the limit could flip | `IsSlaMet` compares exact seconds |
| K7 for a circuit with no backlog: SQL 0, DAX BLANK | `COUNTROWS` of an empty set is BLANK | Same value; the comparison treats BLANK as 0 for counts. The measure keeps BLANK so tables and charts are not filled with zeros |

## AC-02: data quality checks

| Check | Type | Rows affected | Handling | Result |
|---|---|---|---|---|
| SRC-01 Tickets marked as duplicate | Source | 369 | Duplicate, root cause DPC, excluded from KPIs | Pass |
| SRC-02 Overlapping tickets not marked as duplicate | Source | 313 pairs | Kept as valid; listed for the client's review (CR-001) | Pass |
| SRC-03 Restored before opened | Source | 30 | Volume and repeat only | Pass |
| SRC-04 Tickets on circuits missing from inventory | Source | 33 | Inferred circuit, no SLA | Pass |
| SRC-05 Circuits without a region | Source | 76 | Region Unknown | Pass |
| SRC-06 Cancelled tickets | Source | 549 | Excluded from KPIs | Pass |
| INT-01 … INT-06 | Integrity | 0 each | Row reconciliations, flag consistency, backlog reconciliation, referential integrity | Pass |

A source check passes when every affected row is handled by a documented rule; an integrity check passes
when no row breaks it.

## Performance (measured, not estimated)

| What | Result |
|---|---|
| `dw.usp_Refresh`, full rebuild (18,889 tickets → 6 facts and dimensions) | 4.7 s |
| `dw.usp_Refresh`, source unchanged | Skipped in about 10 ms |
| Repeat lookup (K5) without / with the filtered index on the temp table | about 38 ms / 34 ms (3 runs each, `MAXDOP 1`) |
| Power BI full model refresh | 4.4 s |
| Model size in memory (cache.abf) | 1.6 MB |
| Page queries (< 5 s requirement), cold cache | See the next table |

### Page query times

`validation/measure_page_performance.ps1` clears the engine cache before each page and runs the DAX query of
every data visual (extracted with `pbir visuals query`) one after another against the model open in
Power BI Desktop. Desktop runs them in parallel, so the sequential total is an upper bound of query time;
rendering time is not included.

| Page | Visuals measured | Total (ms) | Slowest visual (ms) |
|---|---|---|---|
| Overview | 11 | 152 | 85 |
| SLA and Restoration | 8 | 51 | 15 |
| Repeat and Chronic | 7 | 31 | 6 |
| Backlog and Aging | 7 | 51 | 22 |
| Improvement Actions | 8 | 39 | 8 |
| Data Quality | 7 | 41 | 14 |
| Circuit Detail | 6 | 41 | 21 |

The extractor produces invalid DAX for tables with Top N and for matrices with subtotals on both axes, so those
visuals were timed with equivalent hand-written queries (cold cache): chronic circuit list 33 ms, worst breaches
17 ms, SLA by tier and priority 15 ms, full incident history 53 ms. Every page stays far below 5 seconds of
query time.

## Report best practices (`pbir bpa run`)

| Result | Count | Action |
|---|---|---|
| Errors | 0 | — |
| Drop shadows (accessibility) | 68 → 0 | Disabled in the theme |
| Visuals without alt text | 54 → 0 | Alt text added to every visual |
| Utility page exposed | 1 → 0 | Tooltip page hidden |
| Card without title, card size heuristics, fields per table, visual-level filters | 127 (warnings and info) | Kept on purpose: the card category label names the KPI; detail tables need their columns; visual filters implement the 13-month window, the Top N lists and the root-cause scope |
| Hard-coded colours | 8 | Kept on purpose: sequential blue scale for backlog aging (orange only for more than 30 days) and the grey status line |

`pbir validate --all`: passed.

## Model checks

Done by inspection against the semantic-model review categories (the Tabular Editor BPA was not available):
no bidirectional or many-to-many relationships, no calculated columns, auto date/time disabled, date table
marked, implicit measures discouraged, every measure with a description, format string and display folder, keys
and technical flags hidden, all Power Query steps folding, every measure in `Ready` state after load.

The index gain is small at this volume (about 10%); it is kept because the lookup is the one query whose cost
grows with tickets per circuit, and it costs nothing at this size.

## Functional requirements

| ID | Requirement | Status | Where |
|---|---|---|---|
| FR-01 | Executive page: K1–K5, vs previous month and same month last year, 13-month trend | Delivered | Overview: cards, scorecard (Time Comparison calculation group), trends |
| FR-02 | Filters on every page: month, region, technology, tier, priority | Delivered | Report-level filters in the filter pane, shown in each page header |
| FR-03 | SLA page: K3 and K4 by region, technology, priority, tier; worst 10 breaches | Delivered | SLA and Restoration (MTTR by region and technology in tooltips) |
| FR-04 | Repeat page: K5 trend, K6 count, chronic circuit list | Delivered | Repeat and Chronic |
| FR-05 | Drill-through from a circuit to its incident history | Delivered | Circuit Detail (drill-through on Circuit Id) |
| FR-06 | Backlog page: K7 trend, K8 by region, oldest open tickets | Delivered | Backlog and Aging |
| FR-07 | Improvement page: K9 by type and region, list with before/after | Delivered, extended | Improvement Actions, with a matched control group |
| FR-08 | Root-cause split by region | Delivered | Overview |
| FR-09 | Refresh date on every page | Delivered | Header: data date, processing time, warning on failed run |
| FR-10 | Readable with colour vision deficiency | Delivered | Okabe-Ito based palette (blue/orange, no red-green pairs); values labelled |

## Known limitations

- **Navigator shows the drill-through page.** The `pbir` CLI cannot set the page navigator's
  "show hidden pages" option. In Power BI Desktop: select the navigator → Format → Pages → Show hidden pages: Off.
- **Refresh from outside Power BI Desktop.** A refresh triggered through the local engine (TOM) returned
  cached results after the SQL data changed; only the Desktop's own Refresh button read fresh data. Validation
  was run after a Desktop refresh.
- **Date and number formats follow the viewer's locale** (for example "25 set 2025" on a Portuguese Windows).
- **Circuit Detail without drill-through context** shows the first circuit and every ticket; it is meant to be
  opened by right-clicking a circuit (Drill through → Circuit Detail).
- **Small tables** were resized and their fonts reduced; check names in `dq.CheckResult` were shortened. The
  report shows the new names after the next Desktop refresh.
- **PBIX.** Only the PBIP project is delivered. Open `powerbi/NorthGridOps.pbip` and use File → Save as →
  Power BI file (.pbix) if a single file is needed.
- **Export to Excel** from a visual is limited by Power BI (about 150,000 rows to .xlsx); this data stays far
  below that.
