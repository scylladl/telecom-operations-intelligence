/*
    Step 05: dw.usp_Refresh, the periodic processing job of the analytics layer.

    Business rules of docs/01-business-requirements.md section 7 are applied here, so the
    Power BI measures only add up and divide. KPI windows are read from cfg.KpiParameter
    on every run (AC-04).

    Behaviour (details in docs/03-data-model.md, "Refresh"):
      - One run at a time (application lock); a second caller fails immediately.
      - Skips the run when the source tables, reference tables and KPI parameters are
        unchanged since the last successful run, unless @Force = 1.
      - Rebuilds the dw tables inside one transaction: readers see the previous
        complete result until the commit, and a failure rolls back to it.
      - Every run is logged in dw.RefreshLog with its status, duration and error.

    Usage:  EXEC dw.usp_Refresh;              -- scheduled call
            EXEC dw.usp_Refresh @Force = 1;   -- rebuild even if nothing changed
*/
USE NorthGridOps;
GO

CREATE OR ALTER PROCEDURE dw.usp_Refresh
    @Force bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Started datetime2(3) = SYSDATETIME(),
            @RefreshId int,
            @Lock int;

    EXEC @Lock = sp_getapplock @Resource = N'dw.usp_Refresh', @LockMode = 'Exclusive',
                               @LockOwner = 'Session', @LockTimeout = 0;
    IF @Lock < 0
        THROW 50000, 'dw.usp_Refresh is already running.', 1;

    INSERT INTO dw.RefreshLog (StartedAt, Status, TriggeredBy)
    VALUES (@Started, 'Running', ORIGINAL_LOGIN());
    SET @RefreshId = SCOPE_IDENTITY();

    BEGIN TRY
        /* ---------- parameters ---------- */
        DECLARE @RepeatDays  int = (SELECT ParameterValue FROM cfg.KpiParameter WHERE ParameterCode = 'REPEAT_WINDOW_DAYS'),
                @ChronicMin  int = (SELECT ParameterValue FROM cfg.KpiParameter WHERE ParameterCode = 'CHRONIC_MIN_TICKETS'),
                @ChronicDays int = (SELECT ParameterValue FROM cfg.KpiParameter WHERE ParameterCode = 'CHRONIC_WINDOW_DAYS'),
                @ActionDays  int = (SELECT ParameterValue FROM cfg.KpiParameter WHERE ParameterCode = 'ACTION_EFFECT_WINDOW_DAYS'),
                @DataStart   date,
                @DataAsOf    date,
                @Fingerprint int;

        IF @RepeatDays IS NULL OR @ChronicMin IS NULL OR @ChronicDays IS NULL OR @ActionDays IS NULL
            THROW 50001, 'A KPI parameter is missing in cfg.KpiParameter.', 1;

        SELECT @DataStart = MIN(CAST(OpenedAt AS date)),
               @DataAsOf  = MAX(CAST(OpenedAt AS date))
        FROM ops.Incident;

        IF @DataStart IS NULL
            THROW 50002, 'ops.Incident is empty: load the source data first.', 1;

        /* ---------- change detection ---------- */
        -- A checksum is not collision-proof; it only decides whether a scheduled run can be
        -- skipped. A manual run with @Force = 1 always rebuilds.
        SELECT @Fingerprint = CHECKSUM(
            (SELECT COUNT_BIG(*) FROM ops.Incident),          (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ops.Incident),
            (SELECT COUNT_BIG(*) FROM ops.Circuit),           (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ops.Circuit),
            (SELECT COUNT_BIG(*) FROM ops.Customer),          (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ops.Customer),
            (SELECT COUNT_BIG(*) FROM ops.ImprovementAction), (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ops.ImprovementAction),
            (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(ParameterCode, ParameterValue)) FROM cfg.KpiParameter),
            (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ref.SlaTarget),
            (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ref.RootCause),
            (SELECT CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM ref.Region));

        IF @Force = 0 AND @Fingerprint = (SELECT TOP (1) SourceFingerprint FROM dw.RefreshLog
                                          WHERE Status = 'Succeeded' ORDER BY RefreshId DESC)
        BEGIN
            UPDATE dw.RefreshLog
            SET FinishedAt = SYSDATETIME(), Status = 'Skipped', SourceFingerprint = @Fingerprint,
                DurationMs = DATEDIFF(millisecond, @Started, SYSDATETIME()),
                Message = N'Source unchanged since the last successful run'
            WHERE RefreshId = @RefreshId;
            EXEC sp_releaseapplock @Resource = N'dw.usp_Refresh', @LockOwner = 'Session';
            RETURN;
        END;

        /* ---------- ticket classification ---------- */
        -- A ticket marked as duplicate stays a duplicate while its original is still open.
        -- Opened after the original was closed, it is a new failure: it counts and takes the
        -- original's root cause when it has none (specialist's rule, approved with CR-001).
        DROP TABLE IF EXISTS #Ticket;
        SELECT  i.TicketId,
                i.CircuitId,
                i.PriorityCode,
                i.OpenedAt,
                i.RestoredAt,
                i.ClosedAt,
                i.Status,
                i.ResponsibleTeam,
                i.DuplicateOfTicketId,
                c.IncidentClass,
                RootCauseCode = CASE
                                    WHEN c.IncidentClass = 'Duplicate' THEN 'DPC'
                                    WHEN i.DuplicateOfTicketId IS NOT NULL THEN COALESCE(i.RootCauseCode, o.RootCauseCode, '-')
                                    ELSE COALESCE(i.RootCauseCode, '-')
                                END,
                HasTimestampIssue = CAST(CASE WHEN i.RestoredAt < i.OpenedAt THEN 1 ELSE 0 END AS bit)
        INTO    #Ticket
        FROM    ops.Incident AS i
        LEFT JOIN ops.Incident AS o
               ON o.TicketId = i.DuplicateOfTicketId
        CROSS APPLY (SELECT IncidentClass = CASE
                        WHEN i.IsCancelled = 1 THEN 'Cancelled'
                        WHEN i.DuplicateOfTicketId IS NOT NULL
                             AND NOT (o.ClosedAt IS NOT NULL AND i.OpenedAt > o.ClosedAt) THEN 'Duplicate'
                        ELSE 'Valid'
                     END) AS c;

        CREATE UNIQUE CLUSTERED INDEX IX_Ticket ON #Ticket (TicketId);
        -- supports the repeat lookup: same circuit, restored inside a window before opening
        CREATE INDEX IX_Ticket_Repeat ON #Ticket (CircuitId, RestoredAt) INCLUDE (IncidentClass)
            WHERE IncidentClass = 'Valid';

        BEGIN TRANSACTION;

        TRUNCATE TABLE dw.FactActionEffect;
        TRUNCATE TABLE dw.FactChronicDaily;
        TRUNCATE TABLE dw.FactBacklogDaily;
        TRUNCATE TABLE dw.FactIncident;
        TRUNCATE TABLE dw.DimCircuit;
        TRUNCATE TABLE dw.DimDate;
        TRUNCATE TABLE dw.DimPriority;
        TRUNCATE TABLE dw.DimRootCause;
        TRUNCATE TABLE dw.DimActionType;
        TRUNCATE TABLE dw.DimAgeBucket;
        TRUNCATE TABLE dw.KpiParameter;

        /* ---------- small dimensions ---------- */
        INSERT INTO dw.KpiParameter (ParameterCode, ParameterValue, Unit, Description)
        SELECT ParameterCode, ParameterValue, Unit, Description FROM cfg.KpiParameter;

        INSERT INTO dw.DimPriority (PriorityCode, Priority, SortOrder)
        SELECT PriorityCode, CONCAT(PriorityCode, N' - ', Description), CAST(RIGHT(PriorityCode, 1) AS tinyint)
        FROM ref.Priority;

        INSERT INTO dw.DimRootCause (RootCauseCode, RootCause, IsCustomerAttributable, SortOrder)
        SELECT RootCauseCode, RootCauseName, IsCustomerAttributable,
               CASE RootCauseCode WHEN 'LM' THEN 1 WHEN 'BB' THEN 2 WHEN 'PWR' THEN 3 WHEN 'TPY' THEN 4
                                  WHEN 'CPE' THEN 5 WHEN 'UNK' THEN 6 WHEN 'DPC' THEN 8 ELSE 7 END
        FROM ref.RootCause
        UNION ALL
        SELECT '-', N'Not yet assigned', 0, 9;

        INSERT INTO dw.DimActionType (ActionTypeCode, ActionType)
        SELECT ActionTypeCode, ActionTypeName FROM ref.ActionType;

        INSERT INTO dw.DimAgeBucket (AgeBucketCode, AgeBucket, MinDays, MaxDays)
        VALUES (1, '0-2 days', 0, 2), (2, '3-7 days', 3, 7), (3, '8-15 days', 8, 15),
               (4, '16-30 days', 16, 30), (5, '>30 days', 31, NULL);

        /* ---------- date ---------- */
        WITH n AS (
            SELECT TOP (DATEDIFF(day, @DataStart, @DataAsOf) + 1)
                   d = DATEADD(day, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1, @DataStart)
            FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b
        )
        INSERT INTO dw.DimDate (DateKey, [Date], [Year], [Quarter], MonthNumber, MonthName, YearMonth,
                                MonthLabel, MonthStart, MonthEnd, MonthIndex, IsMonthEnd)
        SELECT  YEAR(d) * 10000 + MONTH(d) * 100 + DAY(d),
                d,
                YEAR(d),
                CONCAT(YEAR(d), '-Q', DATEPART(quarter, d)),
                MONTH(d),
                -- explicit culture: DATENAME follows the login language (Portuguese on this server)
                FORMAT(d, 'MMMM', 'en-US'),
                CONVERT(char(7), d, 126),
                FORMAT(d, 'MMM yyyy', 'en-US'),
                DATEFROMPARTS(YEAR(d), MONTH(d), 1),
                EOMONTH(d),
                DATEDIFF(month, @DataStart, d),
                CASE WHEN d = EOMONTH(d) THEN 1 ELSE 0 END
        FROM n;

        /* ---------- circuit, with inferred members ---------- */
        WITH src AS (
            SELECT  c.CircuitId,
                    c.TechnologyCode,
                    Technology     = COALESCE(t.TechnologyName, N'Unknown'),
                    RegionCode     = COALESCE(r.RegionCode, 'UNK'),
                    Region         = COALESCE(r.RegionName, N'Unknown'),
                    Province       = COALESCE(c.Province, N'Unknown'),
                    c.InstallDate,
                    c.DecommissionDate,
                    c.CustomerId,
                    CustomerName   = COALESCE(cu.CustomerName, N'Unknown'),
                    Segment        = COALESCE(cu.Segment, 'Unknown'),
                    TierCode       = COALESCE(st.TierCode, 'UNKNOWN'),
                    Tier           = COALESCE(st.TierName, N'Unknown'),
                    TierSort       = COALESCE(st.SortOrder, 9),
                    AccountManager = COALESCE(cu.AccountManager, 'Unknown'),
                    IsInferred     = CAST(0 AS bit)
            FROM ops.Circuit AS c
            LEFT JOIN ref.Region      AS r  ON r.RegionCode = c.RegionCode
            LEFT JOIN ref.Technology  AS t  ON t.TechnologyCode = c.TechnologyCode
            LEFT JOIN ops.Customer    AS cu ON cu.CustomerId = c.CustomerId
            LEFT JOIN ref.ServiceTier AS st ON st.TierCode = cu.TierCode
            UNION ALL
            -- circuits referenced by tickets or actions but missing from the inventory
            SELECT  x.CircuitId, 'UNK', N'Unknown', 'UNK', N'Unknown', N'Unknown', NULL, NULL, NULL,
                    N'Unknown', 'Unknown', 'UNKNOWN', N'Unknown', 9, 'Unknown', CAST(1 AS bit)
            FROM (SELECT CircuitId FROM ops.Incident UNION SELECT CircuitId FROM ops.ImprovementAction) AS x
            WHERE NOT EXISTS (SELECT 1 FROM ops.Circuit AS c WHERE c.CircuitId = x.CircuitId)
        )
        INSERT INTO dw.DimCircuit (CircuitKey, CircuitId, TechnologyCode, Technology, RegionCode, Region, Province,
                                   InstallDate, DecommissionDate, CustomerId, CustomerName, Segment, TierCode, Tier,
                                   TierSort, AccountManager, IsInferred, HasImprovementAction)
        SELECT  ROW_NUMBER() OVER (ORDER BY s.CircuitId),
                s.CircuitId, s.TechnologyCode, s.Technology, s.RegionCode, s.Region, s.Province,
                s.InstallDate, s.DecommissionDate, s.CustomerId, s.CustomerName, s.Segment, s.TierCode, s.Tier,
                s.TierSort, s.AccountManager, s.IsInferred,
                CASE WHEN EXISTS (SELECT 1 FROM ops.ImprovementAction AS a WHERE a.CircuitId = s.CircuitId) THEN 1 ELSE 0 END
        FROM src AS s;

        /* ---------- incident fact ---------- */
        INSERT INTO dw.FactIncident (TicketId, CircuitKey, PriorityCode, RootCauseCode, OpenedAt, RestoredAt, ClosedAt,
                                     OpenedDateKey, RestoredDateKey, Status, ResponsibleTeam, IncidentClass,
                                     DuplicateOfTicketId, HasTimestampIssue, IsCounted, IsRestored, RestoreHours,
                                     SlaTargetHours, IsSlaInScope, IsSlaMet, HoursOverTarget, IsRepeat)
        SELECT  t.TicketId,
                dc.CircuitKey,
                t.PriorityCode,
                t.RootCauseCode,
                t.OpenedAt,
                t.RestoredAt,
                t.ClosedAt,
                YEAR(t.OpenedAt) * 10000 + MONTH(t.OpenedAt) * 100 + DAY(t.OpenedAt),
                CASE WHEN m.IsRestored = 1
                     THEN YEAR(t.RestoredAt) * 10000 + MONTH(t.RestoredAt) * 100 + DAY(t.RestoredAt) END,
                t.Status,
                t.ResponsibleTeam,
                t.IncidentClass,
                t.DuplicateOfTicketId,
                t.HasTimestampIssue,
                m.IsCounted,
                m.IsRestored,
                CASE WHEN m.IsRestored = 1 THEN h.RestoreHours END,
                sla.RestoreTargetHours,
                m.IsSlaInScope,
                -- compared in exact seconds: the rounded hours could flip a ticket restored on the limit
                CASE WHEN m.IsSlaInScope = 1 AND h.RestoreSeconds <= sla.RestoreTargetHours * 3600 THEN 1 ELSE 0 END,
                CASE WHEN m.IsSlaInScope = 1 THEN h.RestoreHours - sla.RestoreTargetHours END,
                CASE WHEN m.IsCounted = 1 AND EXISTS (
                        SELECT 1
                        FROM #Ticket AS p
                        WHERE p.CircuitId = t.CircuitId
                          AND p.IncidentClass = 'Valid'
                          AND p.TicketId <> t.TicketId
                          AND p.RestoredAt >= DATEADD(day, -@RepeatDays, t.OpenedAt)
                          AND p.RestoredAt <  t.OpenedAt)
                     THEN 1 ELSE 0 END
        FROM #Ticket AS t
        JOIN dw.DimCircuit AS dc ON dc.CircuitId = t.CircuitId
        LEFT JOIN ref.RootCause AS rc ON rc.RootCauseCode = t.RootCauseCode
        LEFT JOIN ref.SlaTarget AS sla ON sla.TierCode = dc.TierCode AND sla.PriorityCode = t.PriorityCode
        CROSS APPLY (SELECT RestoreSeconds = DATEDIFF(second, t.OpenedAt, t.RestoredAt)) AS s
        CROSS APPLY (SELECT s.RestoreSeconds, RestoreHours = CAST(s.RestoreSeconds / 3600.0 AS decimal(9,2))) AS h
        CROSS APPLY (SELECT IsCounted  = CASE WHEN t.IncidentClass = 'Valid' THEN 1 ELSE 0 END,
                            IsRestored = CASE WHEN t.IncidentClass = 'Valid' AND t.RestoredAt IS NOT NULL
                                               AND t.HasTimestampIssue = 0 THEN 1 ELSE 0 END) AS m0
        CROSS APPLY (SELECT m0.IsCounted,
                            m0.IsRestored,
                            -- customer-premises tickets and circuits without a known tier have no SLA
                            IsSlaInScope = CASE WHEN m0.IsRestored = 1 AND sla.RestoreTargetHours IS NOT NULL
                                                 AND COALESCE(rc.IsCustomerAttributable, 0) = 0 THEN 1 ELSE 0 END) AS m;

        /* ---------- backlog snapshot (K7, K8) ---------- */
        INSERT INTO dw.FactBacklogDaily (SnapshotDateKey, TicketId, CircuitKey, PriorityCode, AgeDays, AgeBucketCode)
        SELECT  d.DateKey,
                f.TicketId,
                f.CircuitKey,
                f.PriorityCode,
                a.AgeDays,
                CASE WHEN a.AgeDays <= 2 THEN 1 WHEN a.AgeDays <= 7 THEN 2 WHEN a.AgeDays <= 15 THEN 3
                     WHEN a.AgeDays <= 30 THEN 4 ELSE 5 END
        FROM dw.FactIncident AS f
        JOIN dw.DimDate AS d
          ON d.[Date] >= CAST(f.OpenedAt AS date)
         AND (f.RestoredAt IS NULL OR d.[Date] < CAST(f.RestoredAt AS date))
        CROSS APPLY (SELECT AgeDays = DATEDIFF(day, CAST(f.OpenedAt AS date), d.[Date])) AS a
        WHERE f.IsCounted = 1
          AND f.HasTimestampIssue = 0;

        /* ---------- chronic circuits (K6) ---------- */
        -- a ticket opened on day t is inside the window of the days t .. t + window - 1
        INSERT INTO dw.FactChronicDaily (SnapshotDateKey, CircuitKey, TicketsInWindow, LastOpenedAt)
        SELECT  d.DateKey, f.CircuitKey, COUNT(*), MAX(f.OpenedAt)
        FROM dw.FactIncident AS f
        JOIN dw.DimDate AS d
          ON d.[Date] >= CAST(f.OpenedAt AS date)
         AND d.[Date] <  DATEADD(day, @ChronicDays, CAST(f.OpenedAt AS date))
        WHERE f.IsCounted = 1
        GROUP BY d.DateKey, f.CircuitKey
        HAVING COUNT(*) >= @ChronicMin;

        /* ---------- improvement action effectiveness (K9) ---------- */
        DROP TABLE IF EXISTS #Action;
        SELECT  a.ActionId,
                dc.CircuitKey,
                dc.TechnologyCode,
                a.ActionTypeCode,
                a.Status,
                a.StartDate,
                a.CompletionDate,
                BeforeStart = DATEADD(day, -@ActionDays, a.StartDate),
                AfterEnd    = DATEADD(day,  @ActionDays, a.CompletionDate),
                EvaluationStatus = CASE
                    WHEN a.Status <> 'Completed' OR a.CompletionDate IS NULL THEN 'Not completed'
                    WHEN dc.IsInferred = 1 THEN 'Circuit missing from inventory'
                    WHEN DATEADD(day, -@ActionDays, a.StartDate) < @DataStart THEN 'Before window starts before the data'
                    WHEN DATEADD(day, @ActionDays, a.CompletionDate) > @DataAsOf THEN 'After window not complete'
                    ELSE 'Evaluated'
                END
        INTO #Action
        FROM ops.ImprovementAction AS a
        JOIN dw.DimCircuit AS dc ON dc.CircuitId = a.CircuitId;

        DROP TABLE IF EXISTS #ActionCount;
        SELECT  a.ActionId,
                IncidentsBefore = COUNT(CASE WHEN o.OpenedDate >= a.BeforeStart AND o.OpenedDate < a.StartDate THEN 1 END),
                IncidentsAfter  = COUNT(CASE WHEN o.OpenedDate > a.CompletionDate AND o.OpenedDate <= a.AfterEnd THEN 1 END)
        INTO #ActionCount
        FROM #Action AS a
        LEFT JOIN dw.FactIncident AS f
               ON f.CircuitKey = a.CircuitKey
              AND f.IsCounted = 1
        OUTER APPLY (SELECT OpenedDate = CAST(f.OpenedAt AS date)) AS o
        WHERE a.EvaluationStatus = 'Evaluated'
        GROUP BY a.ActionId;

        -- Control group: circuits of the same technology that never had an action, active over
        -- both windows, with the same incident count in the before window (6 or more grouped).
        -- Their change over the same dates is what happens without any action (regression to
        -- the mean); the action effect is the difference between both changes.
        DROP TABLE IF EXISTS #ControlCount;
        SELECT  a.ActionId,
                f.CircuitKey,
                Before = COUNT(CASE WHEN o.OpenedDate >= a.BeforeStart AND o.OpenedDate < a.StartDate THEN 1 END),
                After  = COUNT(CASE WHEN o.OpenedDate > a.CompletionDate AND o.OpenedDate <= a.AfterEnd THEN 1 END)
        INTO #ControlCount
        FROM #Action AS a
        JOIN dw.FactIncident AS f
          ON f.IsCounted = 1
         AND f.OpenedAt >= a.BeforeStart
         AND f.OpenedAt <  DATEADD(day, 1, a.AfterEnd)
        JOIN dw.DimCircuit AS dc
          ON dc.CircuitKey = f.CircuitKey
         AND dc.TechnologyCode = a.TechnologyCode
         AND dc.IsInferred = 0
         AND dc.HasImprovementAction = 0
         AND dc.InstallDate <= a.BeforeStart
         AND (dc.DecommissionDate IS NULL OR dc.DecommissionDate > a.AfterEnd)
        CROSS APPLY (SELECT OpenedDate = CAST(f.OpenedAt AS date)) AS o
        WHERE a.EvaluationStatus = 'Evaluated'
        GROUP BY a.ActionId, f.CircuitKey;

        INSERT INTO dw.FactActionEffect (ActionId, CircuitKey, ActionTypeCode, Status, StartDate, CompletionDate,
                                         CompletionDateKey, IsEvaluable, EvaluationStatus, IncidentsBefore,
                                         IncidentsAfter, HasControl, ControlCircuits, ControlBefore, ControlAfter)
        SELECT  a.ActionId,
                a.CircuitKey,
                a.ActionTypeCode,
                a.Status,
                a.StartDate,
                a.CompletionDate,
                dck.DateKey,
                CASE WHEN a.EvaluationStatus = 'Evaluated' THEN 1 ELSE 0 END,
                a.EvaluationStatus,
                ac.IncidentsBefore,
                ac.IncidentsAfter,
                CASE WHEN ctl.Circuits > 0 THEN 1 ELSE 0 END,
                NULLIF(ctl.Circuits, 0),
                ctl.AvgBefore,
                ctl.AvgAfter
        FROM #Action AS a
        LEFT JOIN #ActionCount AS ac ON ac.ActionId = a.ActionId
        LEFT JOIN dw.DimDate AS dck ON dck.[Date] = a.CompletionDate
        OUTER APPLY (SELECT Circuits  = COUNT(*),
                            AvgBefore = CAST(AVG(CAST(cc.Before AS decimal(9,3))) AS decimal(9,3)),
                            AvgAfter  = CAST(AVG(CAST(cc.After  AS decimal(9,3))) AS decimal(9,3))
                     FROM #ControlCount AS cc
                     WHERE cc.ActionId = a.ActionId
                       AND ac.IncidentsBefore > 0
                       AND (cc.Before = ac.IncidentsBefore OR (cc.Before >= 6 AND ac.IncidentsBefore >= 6))) AS ctl;

        COMMIT TRANSACTION;

        UPDATE dw.RefreshLog
        SET FinishedAt = SYSDATETIME(), Status = 'Succeeded', SourceFingerprint = @Fingerprint,
            DataStartDate = @DataStart, DataAsOfDate = @DataAsOf,
            IncidentRows = (SELECT COUNT(*) FROM dw.FactIncident),
            DurationMs = DATEDIFF(millisecond, @Started, SYSDATETIME())
        WHERE RefreshId = @RefreshId;

        EXEC sp_releaseapplock @Resource = N'dw.usp_Refresh', @LockOwner = 'Session';
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        UPDATE dw.RefreshLog
        SET FinishedAt = SYSDATETIME(), Status = 'Failed',
            DurationMs = DATEDIFF(millisecond, @Started, SYSDATETIME()),
            Message = CONCAT(N'Error ', ERROR_NUMBER(), N' at line ', ERROR_LINE(), N': ', ERROR_MESSAGE())
        WHERE RefreshId = @RefreshId;
        IF APPLOCK_MODE('public', N'dw.usp_Refresh', 'Session') <> 'NoLock'
            EXEC sp_releaseapplock @Resource = N'dw.usp_Refresh', @LockOwner = 'Session';
        THROW;
    END CATCH
END;
GO
