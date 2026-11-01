# Change Log

> **SIMULATED SCENARIO.** NorthGrid Telecom and all its data are fictional.

Change requests agreed with the client during development.

| ID | Date | Request | Decision | Where |
|---|---|---|---|---|
| CR-001 | 2026-10-27 | Tickets marked as duplicate arrive without a root cause, mixed with "Not identified". The specialist proposed a dedicated code. | Approved by the Head of B2B Service Assurance with three conditions: (1) the code is described as *not a failure cause* and never appears in the root-cause chart or in any KPI; (2) the number of duplicates per month is visible, because it measures a service-desk process problem; (3) overlapping tickets that were **not** marked as duplicates are not reclassified automatically: they are listed for review first. | `database/03_cr001_duplicate_root_cause.sql` (code `DPC`), `dw.usp_Refresh` (classification), `dq.vw_UnmarkedOverlap` and check SRC-02 (pending review), report page *Data Quality* |

## Open items for the client

- **Unmarked overlapping tickets (CR-001, condition 3).** 313 pairs of valid tickets on the same circuit overlap in time without a duplicate mark (`dq.vw_UnmarkedOverlap`). Some are real parallel failures, some are duplicates nobody marked. A rule (for example "same root cause and opened within N hours") needs the client's approval before it changes any KPI.
- **Duplicate opened after the original was closed.** The specialist's rule treats it as a new failure that takes the original's root cause. No such ticket exists in the current data; the rule is in place for when one appears.
