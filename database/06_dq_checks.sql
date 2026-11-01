/*
    Step 06: data quality checks (schema dq), run after every dw refresh.

    Two kinds of check:
      - Source:    defects in the client exports. They are expected in this data; the check
                   passes when every affected row is handled by a documented dw rule.
      - Integrity: properties the dw layer must always have. Any affected row is a defect.

    Usage:  EXEC dq.usp_RunChecks;
*/
USE NorthGridOps;
GO

IF OBJECT_ID(N'dq.CheckResult') IS NULL
CREATE TABLE dq.CheckResult (
    CheckCode      varchar(10)    NOT NULL CONSTRAINT PK_CheckResult PRIMARY KEY,
    CheckType      varchar(10)    NOT NULL,   -- Source, Integrity
    CheckName      nvarchar(120)  NOT NULL,
    AffectedRows   int            NOT NULL,
    UnhandledRows  int            NOT NULL,
    Handling       nvarchar(300)  NOT NULL,
    Result         varchar(4)     NOT NULL,   -- Pass, Fail
    RunAt          datetime2(0)   NOT NULL
);
GO

-- Pairs of counted tickets on the same circuit that overlap in time without being marked
-- as duplicates. The client asked to review them before any rule reclassifies them.
CREATE OR ALTER VIEW dq.vw_UnmarkedOverlap
AS
SELECT  c.CircuitId,
        a.TicketId    AS FirstTicketId,
        a.OpenedAt    AS FirstOpenedAt,
        a.RestoredAt  AS FirstRestoredAt,
        a.RootCauseCode AS FirstRootCauseCode,
        b.TicketId    AS SecondTicketId,
        b.OpenedAt    AS SecondOpenedAt,
        b.RestoredAt  AS SecondRestoredAt,
        b.RootCauseCode AS SecondRootCauseCode,
        DATEDIFF(minute, a.OpenedAt, b.OpenedAt) AS MinutesBetweenOpenings
FROM dw.FactIncident AS a
JOIN dw.FactIncident AS b
  ON b.CircuitKey = a.CircuitKey
 AND b.TicketId <> a.TicketId
 AND b.IsCounted = 1
 AND (b.OpenedAt > a.OpenedAt OR (b.OpenedAt = a.OpenedAt AND b.TicketId > a.TicketId))
 AND (a.RestoredAt IS NULL OR b.OpenedAt < a.RestoredAt)
JOIN dw.DimCircuit AS c ON c.CircuitKey = a.CircuitKey
WHERE a.IsCounted = 1
  AND a.HasTimestampIssue = 0;
GO

CREATE OR ALTER PROCEDURE dq.usp_RunChecks
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Now datetime2(0) = SYSDATETIME();
    DECLARE @r TABLE (CheckCode varchar(10), CheckType varchar(10), CheckName nvarchar(120),
                      AffectedRows int, UnhandledRows int, Handling nvarchar(300));

    /* ---------- source checks ---------- */
    INSERT INTO @r
    SELECT 'SRC-01', 'Source', N'Tickets marked as duplicate by an agent',
           (SELECT COUNT(*) FROM ops.Incident WHERE DuplicateOfTicketId IS NOT NULL AND IsCancelled = 0),
           (SELECT COUNT(*) FROM dw.FactIncident
             WHERE DuplicateOfTicketId IS NOT NULL AND IncidentClass = 'Duplicate'
               AND (IsCounted = 1 OR RootCauseCode <> 'DPC')),
           N'Classified as Duplicate with root cause DPC; excluded from every KPI (CR-001)';

    INSERT INTO @r
    SELECT 'SRC-02', 'Source', N'Overlapping tickets on one circuit, not marked as duplicate',
           (SELECT COUNT(*) FROM dq.vw_UnmarkedOverlap), 0,
           N'Kept as valid tickets and listed in dq.vw_UnmarkedOverlap until a rule is agreed with the client';

    INSERT INTO @r
    SELECT 'SRC-03', 'Source', N'Tickets restored before they were opened',
           (SELECT COUNT(*) FROM ops.Incident WHERE RestoredAt < OpenedAt),
           (SELECT COUNT(*) FROM dw.FactIncident WHERE HasTimestampIssue = 1 AND (IsRestored = 1 OR IsSlaInScope = 1)),
           N'Counted in volume and repeat KPIs; excluded from MTTR, SLA and backlog';

    INSERT INTO @r
    SELECT 'SRC-04', 'Source', N'Tickets on circuits missing from the network inventory',
           (SELECT COUNT(*) FROM ops.Incident AS i
             WHERE NOT EXISTS (SELECT 1 FROM ops.Circuit AS c WHERE c.CircuitId = i.CircuitId)),
           (SELECT COUNT(*) FROM dw.FactIncident AS f JOIN dw.DimCircuit AS c ON c.CircuitKey = f.CircuitKey
             WHERE c.IsInferred = 1 AND f.IsSlaInScope = 1),
           N'Inferred circuit with Unknown region, technology and tier; counted in volume, no SLA target';

    INSERT INTO @r
    SELECT 'SRC-05', 'Source', N'Circuits without a region',
           (SELECT COUNT(*) FROM ops.Circuit WHERE RegionCode IS NULL),
           (SELECT COUNT(*) FROM dw.DimCircuit AS d JOIN ops.Circuit AS c ON c.CircuitId = d.CircuitId
             WHERE c.RegionCode IS NULL AND d.RegionCode <> 'UNK'),
           N'Region shown as Unknown';

    INSERT INTO @r
    SELECT 'SRC-06', 'Source', N'Cancelled tickets',
           (SELECT COUNT(*) FROM ops.Incident WHERE IsCancelled = 1),
           (SELECT COUNT(*) FROM dw.FactIncident WHERE IncidentClass = 'Cancelled' AND IsCounted = 1),
           N'Excluded from every KPI';

    /* ---------- integrity checks ---------- */
    INSERT INTO @r
    SELECT 'INT-01', 'Integrity', N'Every source ticket is in the incident fact exactly once', x.n, x.n,
           N'Row count reconciliation'
    FROM (SELECT n = ABS((SELECT COUNT(*) FROM ops.Incident) - (SELECT COUNT(*) FROM dw.FactIncident))) AS x;

    INSERT INTO @r
    SELECT 'INT-02', 'Integrity', N'Restored tickets have a non-negative restoration time', x.n, x.n, N'MTTR input'
    FROM (SELECT n = COUNT(*) FROM dw.FactIncident
          WHERE IsRestored = 1 AND (RestoreHours IS NULL OR RestoreHours < 0 OR RestoredDateKey IS NULL)) AS x;

    INSERT INTO @r
    SELECT 'INT-03', 'Integrity', N'KPI flags are consistent (met in scope, in scope restored, restored counted)',
           x.n, x.n, N'K3/K4 inputs'
    FROM (SELECT n = COUNT(*) FROM dw.FactIncident
          WHERE (IsSlaMet = 1 AND IsSlaInScope = 0) OR (IsSlaInScope = 1 AND IsRestored = 0)
             OR (IsRestored = 1 AND IsCounted = 0) OR (IsRepeat = 1 AND IsCounted = 0)) AS x;

    INSERT INTO @r
    SELECT 'INT-04', 'Integrity', N'Backlog on the last day equals counted tickets not yet restored', x.n, x.n,
           N'K7 reconciliation'
    FROM (SELECT n = ABS(
            (SELECT COUNT(*) FROM dw.FactBacklogDaily WHERE SnapshotDateKey = (SELECT MAX(DateKey) FROM dw.DimDate))
          - (SELECT COUNT(*) FROM dw.FactIncident WHERE IsCounted = 1 AND RestoredAt IS NULL))) AS x;

    INSERT INTO @r
    SELECT 'INT-05', 'Integrity', N'Fact rows reference existing dimension members', x.n, x.n,
           N'Referential integrity of the star schema'
    FROM (SELECT n =
            (SELECT COUNT(*) FROM dw.FactIncident AS f WHERE NOT EXISTS (SELECT 1 FROM dw.DimDate AS d WHERE d.DateKey = f.OpenedDateKey))
          + (SELECT COUNT(*) FROM dw.FactIncident AS f WHERE f.RestoredDateKey IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM dw.DimDate AS d WHERE d.DateKey = f.RestoredDateKey))
          + (SELECT COUNT(*) FROM dw.FactIncident AS f WHERE NOT EXISTS (SELECT 1 FROM dw.DimRootCause AS r WHERE r.RootCauseCode = f.RootCauseCode))
          + (SELECT COUNT(*) FROM dw.FactIncident AS f WHERE NOT EXISTS (SELECT 1 FROM dw.DimPriority AS p WHERE p.PriorityCode = f.PriorityCode))
          + (SELECT COUNT(*) FROM dw.FactIncident AS f WHERE NOT EXISTS (SELECT 1 FROM dw.DimCircuit AS c WHERE c.CircuitKey = f.CircuitKey))
          + (SELECT COUNT(*) FROM dw.FactActionEffect AS a WHERE NOT EXISTS (SELECT 1 FROM dw.DimCircuit AS c WHERE c.CircuitKey = a.CircuitKey))) AS x;

    INSERT INTO @r
    SELECT 'INT-06', 'Integrity', N'Every improvement action is in the action fact', x.n, x.n,
           N'Row count reconciliation'
    FROM (SELECT n = ABS((SELECT COUNT(*) FROM ops.ImprovementAction) - (SELECT COUNT(*) FROM dw.FactActionEffect))) AS x;

    BEGIN TRANSACTION;
    DELETE FROM dq.CheckResult;
    INSERT INTO dq.CheckResult (CheckCode, CheckType, CheckName, AffectedRows, UnhandledRows, Handling, Result, RunAt)
    SELECT CheckCode, CheckType, CheckName, AffectedRows, UnhandledRows, Handling,
           CASE WHEN UnhandledRows = 0 THEN 'Pass' ELSE 'Fail' END, @Now
    FROM @r;
    COMMIT TRANSACTION;

    SELECT CheckCode, CheckType, CheckName, AffectedRows, UnhandledRows, Result
    FROM dq.CheckResult
    ORDER BY CheckCode;
END;
GO
