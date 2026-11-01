/*
    Step 03: change request CR-001 (docs/02-change-log.md), approved by the client.

    Tickets that agents mark as duplicate arrive without a root cause. They get their own
    code, DPC, so they are not mixed with "Not identified". DPC is not a failure cause:
    duplicate tickets never count in any KPI; only the original ticket counts.

    Adds one row to ref.RootCause. Safe to run more than once.
*/
USE NorthGridOps;
GO

MERGE ref.RootCause AS t
USING (VALUES ('DPC', N'Duplicate ticket (not a failure cause)', 0))
    AS s (RootCauseCode, RootCauseName, IsCustomerAttributable)
ON t.RootCauseCode = s.RootCauseCode
WHEN MATCHED THEN UPDATE SET RootCauseName = s.RootCauseName, IsCustomerAttributable = s.IsCustomerAttributable
WHEN NOT MATCHED THEN INSERT (RootCauseCode, RootCauseName, IsCustomerAttributable)
    VALUES (s.RootCauseCode, s.RootCauseName, s.IsCustomerAttributable);
GO
