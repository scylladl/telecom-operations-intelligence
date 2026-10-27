# B2B Network Operations Intelligence

> **Status: in progress.** Portfolio project by Scylla Data Lab.
> **Simulated scenario:** NorthGrid Telecom, its customers, data and results are fictional.

A business intelligence solution for the B2B network operations of a (fictional) Spanish
connectivity provider: incident volume, restoration time and SLA compliance, repeat incidents
and chronic circuits, backlog aging and the effectiveness of improvement actions.

Built with SQL Server, T-SQL, Python and Power BI (PBIP).

## What is in the repository

| Path | Content | Owner in the simulation |
|---|---|---|
| `docs/01-business-requirements.md` | Business requirements from the client | Client |
| `docs/00-source-data-handover.md` | Handover note for the source data | Client |
| `database/00_create_database.sql` | Database and schemas | Specialist |
| `database/01_reference_tables.sql` | Reference data and KPI parameters | Client data, specialist's table design |
| `database/02_source_tables.sql` | Simulated source system tables (`ops`) | Client (simulated) |
| `generator/generate_source_data.py` | Synthetic source data, fixed seed | Client (simulated) |
| `database/deploy.ps1`, `database/load_source_data.ps1`, `build.ps1` | Build and load scripts | Specialist |

The analytical layer (`dw`), data quality checks (`dq`) and the Power BI report are being built.

## How to run

Requirements: Windows, SQL Server 2019 or later reachable with Windows authentication,
Python 3.10 or later. No Python packages are needed.

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1 -Server localhost
```

This creates the `NorthGridOps` database, generates two years of synthetic data
(2024–2025) and loads it. Running it again rebuilds the same data.

## Resumen en español

Solución de BI para las operaciones de red B2B de un operador ficticio en España: volumen de
incidencias, tiempo de restablecimiento, cumplimiento de SLA, incidencias repetidas, circuitos
crónicos, backlog y eficacia de las acciones de mejora. Todos los datos son simulados.
