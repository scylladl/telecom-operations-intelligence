/*
    Step 04: dimensional layer (schema dw). Star schema rebuilt by dw.usp_Refresh (step 05).

    Tables are created only when missing; their content belongs to the refresh procedure.
    Grain and keys of every table: docs/03-data-model.md.
*/
USE NorthGridOps;
GO

/* ---------- processing log ---------- */

IF OBJECT_ID(N'dw.RefreshLog') IS NULL
CREATE TABLE dw.RefreshLog (
    RefreshId             int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RefreshLog PRIMARY KEY,
    StartedAt             datetime2(0)   NOT NULL,
    FinishedAt            datetime2(0)   NULL,
    Status                varchar(10)    NOT NULL,   -- Running, Succeeded, Skipped, Failed
    TriggeredBy           nvarchar(128)  NOT NULL,
    SourceFingerprint     int            NULL,       -- checksum of ops tables and KPI parameters
    DataStartDate         date           NULL,
    DataAsOfDate          date           NULL,       -- last complete day in the source extraction
    IncidentRows          int            NULL,
    DurationMs            int            NULL,
    Message               nvarchar(4000) NULL
);
GO

/* ---------- dimensions ---------- */

IF OBJECT_ID(N'dw.DimDate') IS NULL
CREATE TABLE dw.DimDate (
    DateKey      int         NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,   -- yyyymmdd
    [Date]       date        NOT NULL CONSTRAINT UQ_DimDate_Date UNIQUE,
    [Year]       smallint    NOT NULL,
    [Quarter]    char(7)     NOT NULL,   -- 2025-Q1
    MonthNumber  tinyint     NOT NULL,
    MonthName    varchar(10) NOT NULL,
    YearMonth    char(7)     NOT NULL,   -- 2025-03
    MonthLabel   char(8)     NOT NULL,   -- Mar 2025
    MonthStart   date        NOT NULL,
    MonthEnd     date        NOT NULL,
    MonthIndex   int         NOT NULL,   -- 0 = first month of data; sorting and month offsets
    IsMonthEnd   bit         NOT NULL
);

IF OBJECT_ID(N'dw.DimCircuit') IS NULL
CREATE TABLE dw.DimCircuit (
    CircuitKey            int           NOT NULL CONSTRAINT PK_DimCircuit PRIMARY KEY,
    CircuitId             varchar(20)   NOT NULL CONSTRAINT UQ_DimCircuit_Id UNIQUE,
    TechnologyCode        char(3)       NOT NULL,
    Technology            nvarchar(50)  NOT NULL,
    RegionCode            char(3)       NOT NULL,   -- UNK when missing in the source
    Region                nvarchar(50)  NOT NULL,
    Province              nvarchar(40)  NOT NULL,
    InstallDate           date          NULL,
    DecommissionDate      date          NULL,
    CustomerId            int           NULL,
    CustomerName          nvarchar(100) NOT NULL,
    Segment               varchar(20)   NOT NULL,
    TierCode              varchar(7)    NOT NULL,
    Tier                  nvarchar(20)  NOT NULL,
    TierSort              tinyint       NOT NULL,
    AccountManager        varchar(10)   NOT NULL,
    IsInferred            bit           NOT NULL,   -- referenced by tickets, missing from the inventory
    HasImprovementAction  bit           NOT NULL
);

IF OBJECT_ID(N'dw.DimPriority') IS NULL
CREATE TABLE dw.DimPriority (
    PriorityCode  char(2)       NOT NULL CONSTRAINT PK_DimPriority PRIMARY KEY,
    Priority      nvarchar(120) NOT NULL,
    SortOrder     tinyint       NOT NULL
);

IF OBJECT_ID(N'dw.DimRootCause') IS NULL
CREATE TABLE dw.DimRootCause (
    RootCauseCode           varchar(3)   NOT NULL CONSTRAINT PK_DimRootCause PRIMARY KEY,
    RootCause               nvarchar(50) NOT NULL,
    IsCustomerAttributable  bit          NOT NULL,
    SortOrder               tinyint      NOT NULL
);

IF OBJECT_ID(N'dw.DimActionType') IS NULL
CREATE TABLE dw.DimActionType (
    ActionTypeCode  varchar(15)  NOT NULL CONSTRAINT PK_DimActionType PRIMARY KEY,
    ActionType      nvarchar(50) NOT NULL
);

IF OBJECT_ID(N'dw.DimAgeBucket') IS NULL
CREATE TABLE dw.DimAgeBucket (
    AgeBucketCode  tinyint     NOT NULL CONSTRAINT PK_DimAgeBucket PRIMARY KEY,
    AgeBucket      varchar(12) NOT NULL,
    MinDays        int         NOT NULL,
    MaxDays        int         NULL
);

-- KPI parameters used by the last successful refresh (shown in the report)
IF OBJECT_ID(N'dw.KpiParameter') IS NULL
CREATE TABLE dw.KpiParameter (
    ParameterCode   varchar(40)   NOT NULL CONSTRAINT PK_dw_KpiParameter PRIMARY KEY,
    ParameterValue  int           NOT NULL,
    Unit            varchar(20)   NOT NULL,
    Description     nvarchar(200) NOT NULL
);

/* ---------- facts ---------- */

-- One row per source ticket, cancelled and duplicate ones included (IsCounted = 0) so data
-- quality can be reported. KPI components are 1/0 flags and additive numbers: the measures
-- only add up and divide, so ratios stay correct under any filter combination.
IF OBJECT_ID(N'dw.FactIncident') IS NULL
CREATE TABLE dw.FactIncident (
    TicketId             varchar(20)   NOT NULL CONSTRAINT PK_FactIncident PRIMARY KEY,
    CircuitKey           int           NOT NULL,
    PriorityCode         char(2)       NOT NULL,
    RootCauseCode        varchar(3)    NOT NULL,   -- '-' while not assigned, DPC for duplicates
    OpenedAt             datetime2(0)  NOT NULL,
    RestoredAt           datetime2(0)  NULL,
    ClosedAt             datetime2(0)  NULL,
    OpenedDateKey        int           NOT NULL,
    RestoredDateKey      int           NULL,       -- set only for tickets counted in restoration KPIs
    Status               varchar(10)   NOT NULL,
    ResponsibleTeam      nvarchar(40)  NOT NULL,
    IncidentClass        varchar(10)   NOT NULL,   -- Valid, Duplicate, Cancelled
    DuplicateOfTicketId  varchar(20)   NULL,
    HasTimestampIssue    bit           NOT NULL,   -- RestoredAt earlier than OpenedAt in the source
    IsCounted            tinyint       NOT NULL,   -- K1
    IsRestored           tinyint       NOT NULL,   -- K3 denominator
    RestoreHours         decimal(9,2)  NULL,       -- K3 numerator, calendar hours
    SlaTargetHours       decimal(5,1)  NULL,
    IsSlaInScope         tinyint       NOT NULL,   -- K4 denominator
    IsSlaMet             tinyint       NOT NULL,   -- K4 numerator
    HoursOverTarget      decimal(9,2)  NULL,       -- positive for breaches
    IsRepeat             tinyint       NOT NULL    -- K5 numerator
);

-- K7/K8: one row per counted ticket not yet restored at the end of each day
IF OBJECT_ID(N'dw.FactBacklogDaily') IS NULL
CREATE TABLE dw.FactBacklogDaily (
    SnapshotDateKey  int          NOT NULL,
    TicketId         varchar(20)  NOT NULL,
    CircuitKey       int          NOT NULL,
    PriorityCode     char(2)      NOT NULL,
    AgeDays          int          NOT NULL,
    AgeBucketCode    tinyint      NOT NULL,
    CONSTRAINT PK_FactBacklogDaily PRIMARY KEY (SnapshotDateKey, TicketId)
);

-- K6: one row per circuit that is chronic at the end of each day
IF OBJECT_ID(N'dw.FactChronicDaily') IS NULL
CREATE TABLE dw.FactChronicDaily (
    SnapshotDateKey  int           NOT NULL,
    CircuitKey       int           NOT NULL,
    TicketsInWindow  int           NOT NULL,
    LastOpenedAt     datetime2(0)  NOT NULL,
    CONSTRAINT PK_FactChronicDaily PRIMARY KEY (SnapshotDateKey, CircuitKey)
);

-- K9: one row per improvement action, with before/after counts and a matched control group
IF OBJECT_ID(N'dw.FactActionEffect') IS NULL
CREATE TABLE dw.FactActionEffect (
    ActionId            int           NOT NULL CONSTRAINT PK_FactActionEffect PRIMARY KEY,
    CircuitKey          int           NOT NULL,
    ActionTypeCode      varchar(15)   NOT NULL,
    Status              varchar(12)   NOT NULL,
    StartDate           date          NOT NULL,
    CompletionDate      date          NULL,
    CompletionDateKey   int           NULL,
    IsEvaluable         tinyint       NOT NULL,   -- completed, both windows inside the data
    EvaluationStatus    varchar(40)   NOT NULL,
    IncidentsBefore     int           NULL,
    IncidentsAfter      int           NULL,
    HasControl          tinyint       NOT NULL,
    ControlCircuits     int           NULL,       -- untreated circuits used as comparison
    ControlBefore       decimal(9,3)  NULL,       -- average incidents per control circuit
    ControlAfter        decimal(9,3)  NULL
);
GO
