# Technical Decisions

> **SIMULATED SCENARIO.** NorthGrid Telecom and its data are fictional.

Practical notes on why the solution is built the way it is, with the alternatives considered.
Previously agreed decisions are marked **(agreed)**; the rest are technical choices made during development.

## Architecture

### 1. Business rules in SQL, Power BI measures only add and divide (agreed)
The specialist's practice, accepted by the client: heavy processing in SQL Server, the fewest possible
calculated columns in Power BI. Every rule that classifies a ticket (valid, duplicate, cancelled, repeat,
SLA in scope, SLA met) is applied once in `dw.usp_Refresh` and stored as a 1/0 column. The model has **no
calculated columns**.
*Alternative:* DAX calculated columns or Power Query merges. Rejected: rules spread over three layers,
harder to validate against SQL, and the analytics layer must live in SQL Server (requirement section 9).
*Trade-off:* changing a rule needs a SQL deployment and a reprocessing run, not just a model edit.

### 2. Components, not percentages, in the SQL layer
The client's condition: ratios must be correct under any filter. SQL delivers numerators and denominators
per ticket; DAX divides the sums in the current filter context. A pre-aggregated "SLA % by region and month"
table would have been faster to read but wrong for any other slice.

### 3. Persisted `dw` tables plus `rpt` views, not views over `ops`
The repeat rule (EXISTS over a 30-day window), daily backlog and chronic snapshots (731 days × tickets or
circuits) and the control group (each action against every comparable untreated circuit) are too expensive to
run on every Power BI refresh or user query, and their results only change when the source changes. They are
computed once per processing run and stored.
`rpt` views sit on top with explicit columns: Power BI depends on the view contract, not on physical tables,
so `dw` can be restructured without breaking the report.
*Not used:* indexed views. They cannot contain the window logic, `EXISTS`, outer joins or non-deterministic
expressions this layer needs, and they add maintenance cost on every source write.

### 4. Full rebuild with change detection, not incremental processing
Every derived fact depends on look-back windows (30, 60, 90 days), so an incremental load would have to
recompute those windows anyway. The full rebuild takes about 4.7 s. A checksum of the source, reference and
parameter tables lets scheduled runs skip when nothing changed, which gives safe re-execution without
duplicate processing. Details and the path to incremental processing: `docs/03-data-model.md`.

### 5. One transaction, an application lock and a run log
The rebuild runs in a single transaction (readers see the previous complete result until the commit; a failure
rolls back to it), `sp_getapplock` prevents two concurrent runs, and `dw.RefreshLog` records every run with
status, duration, fingerprint and error. `refresh.ps1` exits with an error on failure so an orchestrator can
stop the Power BI refresh. `TRUNCATE` is used only on the job's own `dw` tables; `ops` and `ref` are never
truncated by the processing.

### 6. Data quality: "handled" vs "broken"
Source defects are expected in client exports; failing a check every day because the source has 30 bad
timestamps would teach people to ignore the checks. A source check passes when every affected row is handled by
a documented rule; integrity checks (reconciliations, referential integrity) must have zero affected rows.

## Data rules

### 7. Duplicate tickets: `DPC` root cause (agreed, CR-001)
Proposed by the specialist: duplicates arrive with no root cause, and leaving them blank would mix them with
the other tickets that have none (open or cancelled tickets, 591 in this data). The client approved the code with conditions (not a failure cause, monthly
count visible, no automatic reclassification of unmarked overlaps).

### 8. Inferred circuits instead of dropping tickets
33 tickets reference circuits missing from the inventory. Dropping them would understate volume; assigning
them to a single "Unknown" member would lose the circuit id needed for the incident history. Each missing id
becomes an inferred circuit with Unknown attributes and `IsInferred = 1`.

### 9. SLA compared in exact seconds
Found during validation: comparing the rounded hours (2 decimals) with the target could flip tickets restored
within 36 seconds of the limit. `IsSlaMet` uses `DATEDIFF(second, …)`.

### 10. Explicit culture for month names
Found when the report showed blank cards: `DATENAME` follows the language of the SQL login, which is Portuguese
on this server. `FORMAT(…, 'en-US')` makes the labels independent of the server (only 731 rows, so the
cost of `FORMAT` does not matter here).

### 11. K9 with a matched control group
The requested before/after comparison is shown, but on its own it is misleading: actions are chosen for
circuits that just had incidents, and those circuits improve anyway (regression to the mean). The control
group (same technology, never treated, same incidents in the same before window, same dates) shows that
improvement without any action. The report puts both side by side and the net effect in percentage points.
*Limitation:* matching on technology and incident count only; 162 of 413 evaluated actions have no
untreated circuit with the same count and are excluded from the net effect, not from the requested
comparison. A wider match (count bands, region) is the next refinement.

## Semantic model

### 12. Star schema, single-direction relationships
Facts at their natural grain (ticket, ticket × day, circuit × day, action); dimensions filter facts; no
bidirectional filters, no many-to-many.

### 13. Two date relationships, one inactive
Counts use the opened date, restoration KPIs the restored date. One active relationship (opened) and an
inactive one (restored) activated by `USERELATIONSHIP` in the four restoration base measures. A role-playing
second date table was the alternative; it would double the slicers and confuse the shared month filter.

### 14. Snapshot measures read the last date in context
Backlog and chronic counts are not additive over time. The measures evaluate the snapshot on `MAX('Date'[Date])`,
so a month shows its month-end value, a year its year-end value, and a trend shows one value per month.

### 15. Calculation groups for comparisons and trends
- **Time Comparison** (Selected Month, Prior Month, MoM, Same Month LY, YoY) turns five KPIs into a scorecard
  without 20 extra measures. `ISSELECTEDMEASURE` switches between a relative change (counts, hours) and a
  difference in percentage points (rates), with a dynamic format string.
- **Trend Window** + a disconnected **Trend Month** table give a 13-month trend that ends in the selected month,
  while the month filter still drives the cards. Without it, the month filter would collapse the trend to one
  point.
*Trade-off:* calculation groups are less familiar to some report authors; both are hidden behind visual filters.

### 16. Friendly names in the model, SQL names in the views
Views keep SQL naming (`RestoreHours`); TMDL column names carry the business names (`Restore Hours`) through
`sourceColumn`. No renaming steps in Power Query.

### 17. Power Query: one source step, one type step
Each query reads one `rpt` view and sets the column types explicitly. Both steps fold, so the refresh is one
`SELECT` per table.

## Report

### 18. Report-level filters instead of slicers
FR-02 asks for the same five filters on every page. The CLI used to build the report (`pbir`) cannot create
slicer sync groups, and the project rules forbid hand-editing report JSON. Report-level filters apply the same
selection to every page by construction; each page header shows the active filter context in text.
*Trade-off:* filters live in the filter pane, which some users notice less than slicers.

### 19. One question per page, detail at the bottom
Cards (top) → comparison and trend charts (middle) → detail tables (bottom), on a fixed 1280 × 720 grid with
24 px margins and 16 px gaps. Tables are kept for lists people act on (worst breaches, chronic circuits,
oldest tickets, actions), and they can be exported to Excel.

### 20. Colour
Okabe-Ito based palette: safe for the common colour vision deficiencies (FR-10); blue for good, vermillion for
bad, no red-green pairs. Values are labelled, so colour is never the only cue.

## Tooling

### 21. TMDL authored as text, validated with the TOM in Power BI Desktop
The Tabular Editor CLI was not available. The model was written as TMDL and validated with
`TmdlSerializer` from the libraries shipped with Power BI Desktop (`powerbi/validate_model.ps1`), which reports
the file and line of any error. DAX errors only appear once the model is loaded, so every change was followed
by a check of each measure's state through the local engine.

### 22. Report built with `pbir`, never by editing JSON
Pages, visuals, bindings, filters and formatting were created with the `pbir` CLI and checked with
`pbir validate --all` and real screenshots from Power BI Desktop.

### 23. Validation against independent SQL
The validation queries do **not** read the `dw` layer: they rewrite the rules from the source tables, so a bug
in `dw.usp_Refresh` and in the measures would both show up. This caught one bug in the validation itself
(NULL handling) and confirmed the two dw fixes (decisions 9 and 10).

## Streamlit version

### 24. Same views and same rules, computed in pandas
The app reads the `rpt` views, the contract Power BI already uses, and does what the measures do: it sums the
1/0 components and divides. It neither recomputes business rules nor reads `dw` tables. The data (about 90,000
rows) is loaded once and cached for 15 minutes. Filtering in memory avoids a database round trip per filter change,
and a new processing run still appears without a restart. The KPIs are tested against the
independent validation queries, so the app, Power BI and the source rules are checked against one reference.

### 25. Login with hashed local users
`streamlit-authenticator` with bcrypt hashes in a file that is not committed, and a signed cookie whose key is in
`.env`. The app uses Windows authentication to SQL Server, so no database secret exists. This is enough for one
server. An organisation would use its identity provider through Streamlit's OpenID Connect support
(`st.login`). Every user sees all data, and the server is bound to `localhost`: limitations are listed in
`app/README.md`.
