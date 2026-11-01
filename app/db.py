"""Read-only access to the rpt views, the same contract the Power BI model imports."""
import os

import pandas as pd
import sqlalchemy as sa

# One query per view, with explicit columns (the views are the contract: docs/03-data-model.md).
QUERIES = {
    "date": "SELECT DateKey, [Date], MonthLabel, MonthStart, MonthEnd FROM rpt.vw_Date",
    "circuit": """SELECT CircuitKey, CircuitId, Technology, Region, Province, InstallDate, DecommissionDate,
                         CustomerName, Segment, Tier, TierSort, AccountManager, IsInferred
                  FROM rpt.vw_Circuit""",
    "priority": "SELECT PriorityCode, Priority, SortOrder FROM rpt.vw_Priority",
    "root_cause": "SELECT RootCauseCode, RootCause, SortOrder FROM rpt.vw_RootCause",
    "action_type": "SELECT ActionTypeCode, ActionType FROM rpt.vw_ActionType",
    "age_bucket": "SELECT AgeBucketCode, AgeBucket FROM rpt.vw_AgeBucket",
    "incident": """SELECT TicketId, CircuitKey, PriorityCode, RootCauseCode, OpenedAt, RestoredAt, OpenedDateKey,
                          RestoredDateKey, Status, IncidentClass, IsCounted, IsRestored, RestoreHours,
                          SlaTargetHours, IsSlaInScope, IsSlaMet, HoursOverTarget, IsRepeat
                   FROM rpt.vw_Incident""",
    "backlog": "SELECT SnapshotDateKey, TicketId, CircuitKey, PriorityCode, AgeDays, AgeBucketCode FROM rpt.vw_BacklogDaily",
    "chronic": "SELECT SnapshotDateKey, CircuitKey, TicketsInWindow, LastOpenedAt FROM rpt.vw_ChronicDaily",
    "action": """SELECT ActionId, CircuitKey, ActionTypeCode, Status, StartDate, CompletionDate, IsEvaluable,
                        EvaluationStatus, IncidentsBefore, IncidentsAfter, HasControl, ControlCircuits,
                        ControlBefore, ControlAfter
                 FROM rpt.vw_ActionEffect""",
    "kpi_parameter": "SELECT ParameterCode, ParameterValue, Unit, Description FROM rpt.vw_KpiParameter",
    "dq_check": """SELECT CheckCode, CheckType, CheckName, AffectedRows, UnhandledRows, Handling, Result, RunAt
                   FROM rpt.vw_DataQualityCheck""",
    "status": "SELECT LastSuccessAt, DataAsOfDate, LastRunStatus, LastRunStartedAt FROM rpt.vw_ProcessingStatus",
}


def create_engine() -> sa.Engine:
    # Windows authentication: no password in the configuration. TrustServerCertificate is only for a
    # local server with a self-signed certificate (the same setting as "Encrypt" off in Power BI Desktop).
    url = sa.URL.create(
        "mssql+pyodbc",
        host=os.environ["NORTHGRID_SQL_SERVER"],
        database=os.environ["NORTHGRID_SQL_DATABASE"],
        query={
            "driver": os.environ.get("NORTHGRID_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            "Trusted_Connection": "yes",
            "TrustServerCertificate": os.environ.get("NORTHGRID_SQL_TRUST_SERVER_CERTIFICATE", "no"),
        },
    )
    return sa.create_engine(url)


def read_views(engine: sa.Engine) -> dict[str, pd.DataFrame]:
    with engine.connect() as conn:
        return {name: pd.read_sql(sa.text(sql), conn) for name, sql in QUERIES.items()}

