# Source Data Handover

> **SIMULATED SCENARIO.** NorthGrid Telecom and all its data are fictional.

| | |
|---|---|
| **From** | Head of B2B Service Assurance, NorthGrid Telecom (fictional client) |
| **To** | BI specialist |
| **Date** | 2026-10-27 |
| **Extraction** | Full history from 2024-01-01 to 2025-12-31, extracted 2026-01-01 00:00 (Europe/Madrid) |

Hello,

As agreed in the kick-off, IT has loaded the exports from our operational systems into the
`ops` schema of the `NorthGridOps` database. Reference data (regions, tiers, SLA targets,
root causes, action types) is in the `ref` schema and the KPI rules agreed with the operations
committee are in `cfg.KpiParameter`.

| Table | Source system | Rows | Notes from IT |
|---|---|---|---|
| `ops.Customer` | CRM | 4,000 | One row per customer. Tier is the contracted service level. |
| `ops.Circuit` | Network inventory | 6,497 | One row per circuit, including decommissioned ones. Region is filled by the provisioning team. |
| `ops.Incident` | Ticketing system | 18,889 | One row per ticket. `RestoredAt` is when service came back; `ClosedAt` is when the ticket was administratively closed. Agents can mark a ticket as duplicate of another. |
| `ops.ImprovementAction` | Improvement plan tracker | 558 | One row per action. `CompletionDate` is empty until the action is finished. |

IT copied the exports as they are. They are not validated, and we know our systems are
not perfect. Please tell us what you find.

From here on it's yours: we expect to hear back with your questions, the technical approach
and a delivery plan, as described in `01-business-requirements.md`.

Best regards,
Head of B2B Service Assurance

---

*How the simulated data is produced: `generator/generate_source_data.py` (fixed seed, standard
library only). Rebuild everything with `build.ps1`.*
