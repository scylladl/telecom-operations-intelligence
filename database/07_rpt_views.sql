/*
    Step 07: reporting layer (schema rpt), the only objects Power BI reads.

    One view per semantic model table, with explicit columns. The views are the contract
    between SQL Server and Power BI: dw tables can change without breaking the report as
    long as these columns keep their names and types. They are plain views (no logic,
    no aggregation), so Power Query folds every import into a simple SELECT.
*/
USE NorthGridOps;
GO

IF SCHEMA_ID(N'rpt') IS NULL EXEC (N'CREATE SCHEMA rpt AUTHORIZATION dbo;');
GO

CREATE OR ALTER VIEW rpt.vw_Date AS
SELECT DateKey, [Date], [Year], [Quarter], MonthNumber, MonthName, YearMonth, MonthLabel,
       MonthStart, MonthEnd, MonthIndex, IsMonthEnd
FROM dw.DimDate;
GO

CREATE OR ALTER VIEW rpt.vw_Circuit AS
SELECT CircuitKey, CircuitId, TechnologyCode, Technology, RegionCode, Region, Province,
       InstallDate, DecommissionDate, CustomerId, CustomerName, Segment, TierCode, Tier, TierSort,
       AccountManager, IsInferred, HasImprovementAction
FROM dw.DimCircuit;
GO

CREATE OR ALTER VIEW rpt.vw_Priority AS
SELECT PriorityCode, Priority, SortOrder FROM dw.DimPriority;
GO

CREATE OR ALTER VIEW rpt.vw_RootCause AS
SELECT RootCauseCode, RootCause, IsCustomerAttributable, SortOrder FROM dw.DimRootCause;
GO

CREATE OR ALTER VIEW rpt.vw_ActionType AS
SELECT ActionTypeCode, ActionType FROM dw.DimActionType;
GO

CREATE OR ALTER VIEW rpt.vw_AgeBucket AS
SELECT AgeBucketCode, AgeBucket, MinDays, MaxDays FROM dw.DimAgeBucket;
GO

CREATE OR ALTER VIEW rpt.vw_Incident AS
SELECT TicketId, CircuitKey, PriorityCode, RootCauseCode, OpenedAt, RestoredAt, ClosedAt,
       OpenedDateKey, RestoredDateKey, Status, ResponsibleTeam, IncidentClass, DuplicateOfTicketId,
       HasTimestampIssue, IsCounted, IsRestored, RestoreHours, SlaTargetHours, IsSlaInScope,
       IsSlaMet, HoursOverTarget, IsRepeat
FROM dw.FactIncident;
GO

CREATE OR ALTER VIEW rpt.vw_BacklogDaily AS
SELECT SnapshotDateKey, TicketId, CircuitKey, PriorityCode, AgeDays, AgeBucketCode
FROM dw.FactBacklogDaily;
GO

CREATE OR ALTER VIEW rpt.vw_ChronicDaily AS
SELECT SnapshotDateKey, CircuitKey, TicketsInWindow, LastOpenedAt
FROM dw.FactChronicDaily;
GO

CREATE OR ALTER VIEW rpt.vw_ActionEffect AS
SELECT ActionId, CircuitKey, ActionTypeCode, Status, StartDate, CompletionDate, CompletionDateKey,
       IsEvaluable, EvaluationStatus, IncidentsBefore, IncidentsAfter, HasControl, ControlCircuits,
       ControlBefore, ControlAfter
FROM dw.FactActionEffect;
GO

CREATE OR ALTER VIEW rpt.vw_KpiParameter AS
SELECT ParameterCode, ParameterValue, Unit, Description FROM dw.KpiParameter;
GO

CREATE OR ALTER VIEW rpt.vw_DataQualityCheck AS
SELECT CheckCode, CheckType, CheckName, AffectedRows, UnhandledRows, Handling, Result, RunAt
FROM dq.CheckResult;
GO

-- Last successful processing run, plus the status of the most recent run of any kind,
-- so the report can show when its data was produced and warn when a later run failed.
CREATE OR ALTER VIEW rpt.vw_ProcessingStatus AS
SELECT  s.RefreshId          AS LastSuccessRefreshId,
        s.FinishedAt         AS LastSuccessAt,
        s.DataAsOfDate,
        l.Status             AS LastRunStatus,
        l.StartedAt          AS LastRunStartedAt,
        l.Message            AS LastRunMessage
FROM (SELECT TOP (1) RefreshId, FinishedAt, DataAsOfDate
      FROM dw.RefreshLog WHERE Status = 'Succeeded' ORDER BY RefreshId DESC) AS s
CROSS JOIN (SELECT TOP (1) Status, StartedAt, Message
            FROM dw.RefreshLog WHERE Status <> 'Skipped' ORDER BY RefreshId DESC) AS l;
GO
