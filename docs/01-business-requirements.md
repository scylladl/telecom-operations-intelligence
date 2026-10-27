# Business Requirements — B2B Network Operations Intelligence

> **SIMULATED SCENARIO.** NorthGrid Telecom, its people, data, targets and results are fictional.
> They were created for a portfolio project. Any resemblance to a real company is unintended.

| | |
|---|---|
| **Client** | NorthGrid Telecom S.A. (fictional) — B2B connectivity provider operating in Spain |
| **Sponsor** | Director of Network Operations |
| **Requested by** | Head of B2B Service Assurance |
| **Document status** | v0.1 — kick-off draft, open for questions from the BI specialist |
| **Date** | 2026-10-27 |

## 1. Business context

NorthGrid sells dedicated internet, MPLS/VPN and fixed-wireless access to about 4,000 business
customers through roughly 6,000 circuits, across six service regions in Spain. Field operations are
organised by region; network engineering (backbone/core) is central.

Contracts include restoration-time SLAs by service tier. Over the last year:

- Customers complain that **the same circuits keep failing**. Account managers hear about it before operations does.
- Regional teams report **backlog** in weekly spreadsheets, each with its own definitions. Totals never match.
- The company started **improvement actions** on problem circuits (site surveys, equipment replacement,
  re-routing, technology migration), but **nobody can say whether they work**.

Every Monday the leadership meeting spends the first 30 minutes arguing about whose numbers are right.

## 2. Business problem

> "I need one version of the truth about incidents, restoration, repeat failures and backlog,
> by region, technology and customer tier — and I need to know if the money we spend on
> improvement actions is reducing failures." — Director of Network Operations

## 3. Stakeholders

| Role | Interest | Uses the report for |
|---|---|---|
| Director of Network Operations (sponsor) | Overall performance, budget for improvement actions | Monthly review, board reporting |
| Head of B2B Service Assurance (requester, day-to-day contact) | SLA compliance, repeat incidents | Weekly leadership meeting |
| Regional Field Operations Managers (6) | Their region's backlog and aging | Daily and weekly follow-up |
| Network Engineering Manager | Backbone/core-caused incidents | Monthly root-cause review |
| Key Account Managers | Chronic circuits of their customers | Customer meetings |
| Service Quality Analysts | Detail, validation, ad-hoc analysis | Investigation and data checks |

## 4. Objectives

1. One agreed definition and one source for every operational KPI listed in section 7.
2. See SLA compliance and restoration time by region, technology, tier and priority.
3. Identify **repeat incidents** and **chronic circuits** early.
4. Track **backlog and aging** with the same rules for every region.
5. Measure whether **improvement actions** reduce incidents on the circuits where they were done.

## 5. Scope

### In scope (version 1)

- Executive overview with the main KPIs and trends.
- SLA and restoration analysis.
- Repeat incidents and chronic circuits, with a drill-down to the circuit and its incident history.
- Open backlog and aging, by day.
- Improvement action effectiveness (before and after).
- Data model, KPI dictionary and validation queries documented.

### Out of scope (version 1)

- Real-time monitoring (the report is refreshed once a day).
- Forecasting.
- Financial impact (SLA credits) — may come later.
- Data entry or workflow (handled by another project).

## 6. Data available (simulated)

The specialist will receive or generate these datasets. 24 months of history: January 2024 – December 2025.

| Dataset | Grain | Main fields |
|---|---|---|
| Customers | One row per customer | customer id, name (fake), segment (SME, Corporate, Public sector), tier (Gold, Silver, Bronze), account manager |
| Circuits | One row per circuit | circuit id, customer, technology (Fiber, Fixed Wireless, Copper legacy), region, province, install date, decommission date |
| Incidents (tickets) | One row per ticket | ticket id, circuit, priority (P1–P4), opened at, restored at, closed at, status, root-cause category, responsible team, cancelled flag |
| Improvement actions | One row per action | action id, circuit, action type, start date, completion date, status |
| SLA targets | One row per tier and priority | restoration target in hours |

Root-cause categories: Last mile, Backbone/Core, Customer premises, Power, Third party, Not identified.

All timestamps are local time, **Europe/Madrid**.

## 7. KPIs and business rules

General rules (apply to every KPI unless stated):

- **Cancelled and duplicate tickets are excluded** from every KPI.
- Counts of incidents use the **opened date**; restoration KPIs use the **restored date**.
- Restoration time uses **calendar hours** in version 1.
- Tickets with root cause **Customer premises** count in volume and repeat KPIs, but are **excluded from SLA
  compliance**, because the company is not responsible for them.

| # | KPI | Definition | Grain / period |
|---|---|---|---|
| K1 | Incident volume | Number of tickets opened | Day, month; any dimension |
| K2 | Incidents per 100 circuits | K1 ÷ active circuits at the end of the period × 100 | Month |
| K3 | MTTR (hours) | Average of (restored at − opened at) for restored tickets | Month |
| K4 | SLA compliance % | Restored tickets within the tier and priority target ÷ restored tickets in scope | Month |
| K5 | Repeat incident rate % | Tickets whose circuit had **another non-cancelled ticket restored in the 30 days before** this ticket was opened ÷ all tickets | Month |
| K6 | Chronic circuits | Circuits with **3 or more tickets in the last 60 days**, evaluated at the end of each day | Day snapshot; shown at month end |
| K7 | Open backlog | Tickets opened and not yet restored at the end of the day | Day snapshot |
| K8 | Backlog aging | K7 split into buckets by days open: 0–2, 3–7, 8–15, 16–30, more than 30 | Day snapshot |
| K9 | Action effectiveness | For circuits with a completed action: incidents in the **90 days before** the start date vs the **90 days after** the completion date. Only circuits with 90 full days after completion are counted | Per action; aggregated by action type |

The repeat window (30 days), the chronic rule (3 tickets in 60 days) and the before/after window (90 days)
must be **parameters**, not hard-coded, because the operations committee may change them.

## 8. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Executive page: K1–K5 for the selected month, change vs previous month and vs same month last year, 13-month trend | Must |
| FR-02 | Filters on every page: month, region, technology, customer tier, priority | Must |
| FR-03 | SLA page: K3 and K4 by region, technology, priority and tier; list of the worst 10 breaches of the month | Must |
| FR-04 | Repeat page: K5 trend, K6 count, list of chronic circuits with customer, technology and last incident | Must |
| FR-05 | Drill-through from a circuit to its full incident history | Must |
| FR-06 | Backlog page: K7 trend and K8 by region, with the oldest open tickets | Must |
| FR-07 | Improvement page: K9 by action type and region, list of actions with before and after values | Must |
| FR-08 | Root-cause split of incidents by region | Should |
| FR-09 | Each page shows the data refresh date | Should |
| FR-10 | Report readable for people with colour vision deficiency | Should |

## 9. Non-functional and technical requirements

- **Source:** SQL Server (on-premises). The analytics layer must live in SQL Server, not only inside Power BI.
- **Report:** Power BI Desktop, **Import** mode, saved as **PBIP** so it can be versioned in Git.
- **Licensing constraint:** no Premium, Fabric or paid custom visuals. Built-in visuals only.
- **Language:** English (the group reports in English). Spanish labels may be requested later.
- **Refresh:** daily, after 06:00. Document how the refresh would be scheduled.
- **Performance:** each page should load in under 5 seconds on a standard laptop.
- **Reproducibility:** another analyst must be able to rebuild database and data from scripts.
- **Data quality:** automated checks for duplicates, restored-before-opened timestamps, tickets on unknown
  circuits, and circuits without a region.

## 10. Deliverables

1. Database scripts: staging, operational and dimensional (star schema) layers.
2. Synthetic data generator with a fixed seed.
3. Data quality checks that can be run on demand.
4. Power BI report (PBIP) with the pages in section 8.
5. KPI dictionary: definition, formula, grain, filters, owner.
6. Data model document: tables, grain, relationships, refresh.
7. Validation evidence: each main measure checked against a SQL query.
8. README with business context, architecture, how to run, limitations.

## 11. Acceptance criteria

- AC-01 One documented command rebuilds the database and loads the data from zero.
- AC-02 All data quality checks pass on the generated data.
- AC-03 K1, K3, K4, K5, K7 and K9 in Power BI match the SQL validation queries for at least three test cases each
  (one month total, one region, one circuit).
- AC-04 Changing a KPI parameter (e.g. repeat window 30 → 15 days) changes the results without editing code.
- AC-05 All Must requirements are delivered; Should requirements delivered or explicitly postponed.
- AC-06 Screenshots in the README come from the real report after it was opened and checked.
- AC-07 No real company, customer, person or confidential rule appears anywhere in the project.

## 12. Assumptions and constraints

- All data is synthetic and labelled as such. Any result is simulated.
- The specialist works alone; the Head of B2B Service Assurance answers questions within one business day.
- Budget is fixed: no new licences.

## 13. Open questions for the specialist

The client expects the specialist to come back with:

1. Questions about anything unclear or inconsistent in this document.
2. A proposed technical approach (layers, data model, refresh).
3. A delivery plan in milestones, with what will be shown at each one.
4. Risks and anything the specialist recommends doing differently.

---

*Change requests during development will be recorded in `docs/02-change-log.md`.*
