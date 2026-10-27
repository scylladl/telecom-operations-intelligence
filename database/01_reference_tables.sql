/*
    Step 01: KPI parameters and reference tables, with their seed values.
    Safe to run more than once: tables are created only if missing and
    seed rows are upserted with MERGE.

    Values are fictional (see docs/01-business-requirements.md).
*/
USE NorthGridOps;
GO

SET XACT_ABORT ON;
GO

/* ---------- tables ---------- */

IF OBJECT_ID(N'cfg.KpiParameter') IS NULL
CREATE TABLE cfg.KpiParameter (
    ParameterCode   varchar(40)   NOT NULL CONSTRAINT PK_KpiParameter PRIMARY KEY,
    ParameterValue  int           NOT NULL,
    Unit            varchar(20)   NOT NULL,
    Description     nvarchar(200) NOT NULL,
    UpdatedAt       datetime2(0)  NOT NULL CONSTRAINT DF_KpiParameter_UpdatedAt DEFAULT SYSDATETIME()
);

IF OBJECT_ID(N'ref.Region') IS NULL
CREATE TABLE ref.Region (
    RegionCode  char(3)       NOT NULL CONSTRAINT PK_Region PRIMARY KEY,
    RegionName  nvarchar(50)  NOT NULL CONSTRAINT UQ_Region_Name UNIQUE,
    Coverage    nvarchar(200) NOT NULL
);

IF OBJECT_ID(N'ref.Technology') IS NULL
CREATE TABLE ref.Technology (
    TechnologyCode  char(3)      NOT NULL CONSTRAINT PK_Technology PRIMARY KEY,
    TechnologyName  nvarchar(50) NOT NULL CONSTRAINT UQ_Technology_Name UNIQUE
);

IF OBJECT_ID(N'ref.ServiceTier') IS NULL
CREATE TABLE ref.ServiceTier (
    TierCode   varchar(6)   NOT NULL CONSTRAINT PK_ServiceTier PRIMARY KEY,
    TierName   nvarchar(20) NOT NULL,
    SortOrder  tinyint      NOT NULL
);

IF OBJECT_ID(N'ref.Priority') IS NULL
CREATE TABLE ref.Priority (
    PriorityCode  char(2)       NOT NULL CONSTRAINT PK_Priority PRIMARY KEY,
    Description   nvarchar(100) NOT NULL
);

IF OBJECT_ID(N'ref.SlaTarget') IS NULL
CREATE TABLE ref.SlaTarget (
    TierCode            varchar(6)   NOT NULL CONSTRAINT FK_SlaTarget_Tier REFERENCES ref.ServiceTier (TierCode),
    PriorityCode        char(2)      NOT NULL CONSTRAINT FK_SlaTarget_Priority REFERENCES ref.Priority (PriorityCode),
    RestoreTargetHours  decimal(5,1) NOT NULL CONSTRAINT CK_SlaTarget_Hours CHECK (RestoreTargetHours > 0),
    CONSTRAINT PK_SlaTarget PRIMARY KEY (TierCode, PriorityCode)
);

IF OBJECT_ID(N'ref.RootCause') IS NULL
CREATE TABLE ref.RootCause (
    RootCauseCode             varchar(3)   NOT NULL CONSTRAINT PK_RootCause PRIMARY KEY,
    RootCauseName             nvarchar(50) NOT NULL,
    -- customer-attributable incidents are excluded from SLA compliance (business rule K4)
    IsCustomerAttributable    bit          NOT NULL
);

IF OBJECT_ID(N'ref.ActionType') IS NULL
CREATE TABLE ref.ActionType (
    ActionTypeCode  varchar(15)  NOT NULL CONSTRAINT PK_ActionType PRIMARY KEY,
    ActionTypeName  nvarchar(50) NOT NULL
);
GO

/* ---------- seed data ---------- */

BEGIN TRANSACTION;

MERGE cfg.KpiParameter AS t
USING (VALUES
    ('REPEAT_WINDOW_DAYS',        30, 'days',    N'A ticket is a repeat if the circuit had another ticket restored in this many days before it opened (K5)'),
    ('CHRONIC_MIN_TICKETS',        3, 'tickets', N'Minimum tickets in the chronic window for a circuit to be chronic (K6)'),
    ('CHRONIC_WINDOW_DAYS',       60, 'days',    N'Rolling window used by the chronic circuit rule (K6)'),
    ('ACTION_EFFECT_WINDOW_DAYS', 90, 'days',    N'Days before the action start and after its completion compared by K9')
) AS s (ParameterCode, ParameterValue, Unit, Description)
ON t.ParameterCode = s.ParameterCode
WHEN NOT MATCHED THEN
    INSERT (ParameterCode, ParameterValue, Unit, Description)
    VALUES (s.ParameterCode, s.ParameterValue, s.Unit, s.Description);
-- existing values are kept on purpose: the committee may have changed them

MERGE ref.Region AS t
USING (VALUES
    ('NOR', N'North',     N'Basque Country, Cantabria, Navarre, La Rioja'),
    ('NEA', N'Northeast', N'Catalonia, Aragon, Balearic Islands'),
    ('EST', N'East',      N'Valencian Community, Region of Murcia'),
    ('CEN', N'Center',    N'Madrid, Castile and Leon, Castile-La Mancha, Extremadura'),
    ('SUR', N'South',     N'Andalusia, Canary Islands, Ceuta, Melilla'),
    ('NWE', N'Northwest', N'Galicia, Asturias')
) AS s (RegionCode, RegionName, Coverage)
ON t.RegionCode = s.RegionCode
WHEN MATCHED THEN UPDATE SET RegionName = s.RegionName, Coverage = s.Coverage
WHEN NOT MATCHED THEN INSERT (RegionCode, RegionName, Coverage) VALUES (s.RegionCode, s.RegionName, s.Coverage);

MERGE ref.Technology AS t
USING (VALUES ('FIB', N'Fiber'), ('FWA', N'Fixed Wireless'), ('COP', N'Copper (legacy)'))
    AS s (TechnologyCode, TechnologyName)
ON t.TechnologyCode = s.TechnologyCode
WHEN MATCHED THEN UPDATE SET TechnologyName = s.TechnologyName
WHEN NOT MATCHED THEN INSERT (TechnologyCode, TechnologyName) VALUES (s.TechnologyCode, s.TechnologyName);

MERGE ref.ServiceTier AS t
USING (VALUES ('GOLD', N'Gold', 1), ('SILVER', N'Silver', 2), ('BRONZE', N'Bronze', 3))
    AS s (TierCode, TierName, SortOrder)
ON t.TierCode = s.TierCode
WHEN MATCHED THEN UPDATE SET TierName = s.TierName, SortOrder = s.SortOrder
WHEN NOT MATCHED THEN INSERT (TierCode, TierName, SortOrder) VALUES (s.TierCode, s.TierName, s.SortOrder);

MERGE ref.Priority AS t
USING (VALUES
    ('P1', N'Total outage'),
    ('P2', N'Severe degradation'),
    ('P3', N'Partial degradation'),
    ('P4', N'Minor issue or information request')
) AS s (PriorityCode, Description)
ON t.PriorityCode = s.PriorityCode
WHEN MATCHED THEN UPDATE SET Description = s.Description
WHEN NOT MATCHED THEN INSERT (PriorityCode, Description) VALUES (s.PriorityCode, s.Description);

MERGE ref.SlaTarget AS t
USING (VALUES
    ('GOLD',   'P1',  4.0), ('GOLD',   'P2',  6.0), ('GOLD',   'P3', 12.0), ('GOLD',   'P4', 24.0),
    ('SILVER', 'P1',  6.0), ('SILVER', 'P2',  8.0), ('SILVER', 'P3', 24.0), ('SILVER', 'P4', 48.0),
    ('BRONZE', 'P1',  8.0), ('BRONZE', 'P2', 12.0), ('BRONZE', 'P3', 48.0), ('BRONZE', 'P4', 72.0)
) AS s (TierCode, PriorityCode, RestoreTargetHours)
ON t.TierCode = s.TierCode AND t.PriorityCode = s.PriorityCode
WHEN MATCHED THEN UPDATE SET RestoreTargetHours = s.RestoreTargetHours
WHEN NOT MATCHED THEN INSERT (TierCode, PriorityCode, RestoreTargetHours) VALUES (s.TierCode, s.PriorityCode, s.RestoreTargetHours);

MERGE ref.RootCause AS t
USING (VALUES
    ('LM',  N'Last mile',         0),
    ('BB',  N'Backbone/Core',     0),
    ('CPE', N'Customer premises', 1),
    ('PWR', N'Power',             0),
    ('TPY', N'Third party',       0),
    ('UNK', N'Not identified',    0)
) AS s (RootCauseCode, RootCauseName, IsCustomerAttributable)
ON t.RootCauseCode = s.RootCauseCode
WHEN MATCHED THEN UPDATE SET RootCauseName = s.RootCauseName, IsCustomerAttributable = s.IsCustomerAttributable
WHEN NOT MATCHED THEN INSERT (RootCauseCode, RootCauseName, IsCustomerAttributable) VALUES (s.RootCauseCode, s.RootCauseName, s.IsCustomerAttributable);

MERGE ref.ActionType AS t
USING (VALUES
    ('SITE_SURVEY',    N'Site survey'),
    ('EQUIP_REPLACE',  N'Equipment replacement'),
    ('REROUTE',        N'Re-routing'),
    ('TECH_MIGRATION', N'Technology migration')
) AS s (ActionTypeCode, ActionTypeName)
ON t.ActionTypeCode = s.ActionTypeCode
WHEN MATCHED THEN UPDATE SET ActionTypeName = s.ActionTypeName
WHEN NOT MATCHED THEN INSERT (ActionTypeCode, ActionTypeName) VALUES (s.ActionTypeCode, s.ActionTypeName);

COMMIT TRANSACTION;
GO
