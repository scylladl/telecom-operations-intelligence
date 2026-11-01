/*
    Validation queries (AC-03): K1, K3, K4, K5, K7 and K9 computed straight from the source
    tables (ops, ref, cfg), without the dw layer, for three test cases each.

    The rules are written again here on purpose, in a different form from dw.usp_Refresh,
    so the comparison with the Power BI measures checks the whole chain:
    source -> dw -> rpt -> semantic model -> DAX.

    Output: one row per test case. Run by validation\run_validation.ps1.
*/
SET NOCOUNT ON;

DECLARE @RepeatDays int  = (SELECT ParameterValue FROM cfg.KpiParameter WHERE ParameterCode = 'REPEAT_WINDOW_DAYS'),
        @ActionDays int  = (SELECT ParameterValue FROM cfg.KpiParameter WHERE ParameterCode = 'ACTION_EFFECT_WINDOW_DAYS'),
        @DataStart  date = (SELECT MIN(CAST(OpenedAt AS date)) FROM ops.Incident),
        @DataAsOf   date = (SELECT MAX(CAST(OpenedAt AS date)) FROM ops.Incident);

WITH TestCase AS (
    SELECT * FROM (VALUES
        (1, 'Month Dec 2025',                      CAST('2025-12-01' AS date), CAST('2025-12-31' AS date), CAST(NULL AS char(3)), CAST(NULL AS varchar(20))),
        (2, 'Region South, Dec 2025',              '2025-12-01', '2025-12-31', 'SUR', NULL),
        (3, 'Circuit NG-FWA-001453, all months',   '2024-01-01', '2025-12-31', NULL,  'NG-FWA-001453')
    ) AS t (CaseId, CaseName, FromDate, ToDate, RegionCode, CircuitId)
),
-- valid tickets: not cancelled, and not a duplicate of a ticket still open when it was opened
Valid AS (
    SELECT  i.TicketId, i.CircuitId, i.PriorityCode, i.OpenedAt, i.RestoredAt,
            c.RegionCode, cu.TierCode,
            IsCustomerAttributable = COALESCE(rc.IsCustomerAttributable, 0)
    FROM ops.Incident AS i
    LEFT JOIN ops.Incident  AS o  ON o.TicketId = i.DuplicateOfTicketId
    LEFT JOIN ops.Circuit   AS c  ON c.CircuitId = i.CircuitId
    LEFT JOIN ops.Customer  AS cu ON cu.CustomerId = c.CustomerId
    LEFT JOIN ref.RootCause AS rc ON rc.RootCauseCode = COALESCE(i.RootCauseCode, o.RootCauseCode)
    WHERE i.IsCancelled = 0
      AND (i.DuplicateOfTicketId IS NULL OR i.OpenedAt > o.ClosedAt)
)
SELECT  tc.CaseId,
        tc.CaseName,
        K1_Incidents = (SELECT COUNT(*) FROM Valid AS v
                        WHERE CAST(v.OpenedAt AS date) BETWEEN tc.FromDate AND tc.ToDate
                          AND (tc.RegionCode IS NULL OR v.RegionCode = tc.RegionCode)
                          AND (tc.CircuitId IS NULL OR v.CircuitId = tc.CircuitId)),
        K3_MttrHours = (SELECT SUM(DATEDIFF(second, v.OpenedAt, v.RestoredAt)) / 3600.0 / NULLIF(COUNT(*), 0)
                        FROM Valid AS v
                        WHERE CAST(v.RestoredAt AS date) BETWEEN tc.FromDate AND tc.ToDate
                          AND v.RestoredAt >= v.OpenedAt
                          AND (tc.RegionCode IS NULL OR v.RegionCode = tc.RegionCode)
                          AND (tc.CircuitId IS NULL OR v.CircuitId = tc.CircuitId)),
        K4_SlaPct    = (SELECT 1.0 * SUM(CASE WHEN DATEDIFF(second, v.OpenedAt, v.RestoredAt) <= s.RestoreTargetHours * 3600 THEN 1 ELSE 0 END)
                               / NULLIF(COUNT(*), 0)
                        FROM Valid AS v
                        JOIN ref.SlaTarget AS s ON s.TierCode = v.TierCode AND s.PriorityCode = v.PriorityCode
                        WHERE CAST(v.RestoredAt AS date) BETWEEN tc.FromDate AND tc.ToDate
                          AND v.RestoredAt >= v.OpenedAt
                          AND v.IsCustomerAttributable = 0
                          AND (tc.RegionCode IS NULL OR v.RegionCode = tc.RegionCode)
                          AND (tc.CircuitId IS NULL OR v.CircuitId = tc.CircuitId)),
        K5_RepeatPct = 1.0 * (SELECT COUNT(*) FROM Valid AS v
                              WHERE CAST(v.OpenedAt AS date) BETWEEN tc.FromDate AND tc.ToDate
                                AND (tc.RegionCode IS NULL OR v.RegionCode = tc.RegionCode)
                                AND (tc.CircuitId IS NULL OR v.CircuitId = tc.CircuitId)
                                AND EXISTS (SELECT 1 FROM Valid AS p
                                            WHERE p.CircuitId = v.CircuitId AND p.TicketId <> v.TicketId
                                              AND p.RestoredAt >= DATEADD(day, -@RepeatDays, v.OpenedAt)
                                              AND p.RestoredAt < v.OpenedAt))
                     / NULLIF((SELECT COUNT(*) FROM Valid AS v
                               WHERE CAST(v.OpenedAt AS date) BETWEEN tc.FromDate AND tc.ToDate
                                 AND (tc.RegionCode IS NULL OR v.RegionCode = tc.RegionCode)
                                 AND (tc.CircuitId IS NULL OR v.CircuitId = tc.CircuitId)), 0),
        K7_Backlog   = (SELECT COUNT(*) FROM Valid AS v
                        WHERE CAST(v.OpenedAt AS date) <= tc.ToDate
                          AND (v.RestoredAt IS NULL OR CAST(v.RestoredAt AS date) > tc.ToDate)
                          AND (v.RestoredAt IS NULL OR v.RestoredAt >= v.OpenedAt)   -- NOT (a < b) would drop the NULLs
                          AND (tc.RegionCode IS NULL OR v.RegionCode = tc.RegionCode)
                          AND (tc.CircuitId IS NULL OR v.CircuitId = tc.CircuitId)),
        -- K9 is evaluated per action over fixed windows, so the case month does not apply
        K9_Before    = k9.Before,
        K9_After     = k9.After
FROM TestCase AS tc
CROSS APPLY (
    SELECT  Before = SUM(x.Before), After = SUM(x.After)
    FROM ops.ImprovementAction AS a
    JOIN ops.Circuit AS c ON c.CircuitId = a.CircuitId
    CROSS APPLY (SELECT Before = (SELECT COUNT(*) FROM Valid AS v WHERE v.CircuitId = a.CircuitId
                                    AND CAST(v.OpenedAt AS date) >= DATEADD(day, -@ActionDays, a.StartDate)
                                    AND CAST(v.OpenedAt AS date) <  a.StartDate),
                        After  = (SELECT COUNT(*) FROM Valid AS v WHERE v.CircuitId = a.CircuitId
                                    AND CAST(v.OpenedAt AS date) >  a.CompletionDate
                                    AND CAST(v.OpenedAt AS date) <= DATEADD(day, @ActionDays, a.CompletionDate))) AS x
    WHERE a.Status = 'Completed'
      AND a.CompletionDate IS NOT NULL
      AND DATEADD(day, -@ActionDays, a.StartDate) >= @DataStart
      AND DATEADD(day,  @ActionDays, a.CompletionDate) <= @DataAsOf
      AND (tc.RegionCode IS NULL OR c.RegionCode = tc.RegionCode)
      AND (tc.CircuitId IS NULL OR a.CircuitId = tc.CircuitId)
) AS k9
ORDER BY tc.CaseId;
