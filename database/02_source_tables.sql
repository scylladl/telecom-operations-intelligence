/*
    Step 02: SIMULATED CLIENT SOURCE SYSTEM (schema ops).

    These tables stand for the exports NorthGrid (fictional) would hand to the BI specialist
    from its ticketing system, network inventory and CRM. They are filled by
    generator/generate_source_data.py and are deliberately imperfect, like real source data:
    no foreign keys, a few duplicates and inconsistent timestamps. Cleaning them is part of
    the specialist's work (schemas dw and dq).

    Safe to run more than once.
*/
USE NorthGridOps;
GO

IF OBJECT_ID(N'ops.Customer') IS NULL
CREATE TABLE ops.Customer (
    CustomerId      int           NOT NULL CONSTRAINT PK_ops_Customer PRIMARY KEY,
    CustomerName    nvarchar(100) NOT NULL,
    Segment         varchar(20)   NOT NULL,   -- SME, Corporate, Public sector
    TierCode        varchar(6)    NOT NULL,   -- GOLD, SILVER, BRONZE
    AccountManager  varchar(10)   NOT NULL,
    CreatedDate     date          NOT NULL
);

IF OBJECT_ID(N'ops.Circuit') IS NULL
CREATE TABLE ops.Circuit (
    CircuitId         varchar(20)  NOT NULL CONSTRAINT PK_ops_Circuit PRIMARY KEY,
    CustomerId        int          NOT NULL,
    TechnologyCode    char(3)      NOT NULL,
    RegionCode        char(3)      NULL,       -- missing for a few circuits in the source
    Province          nvarchar(40) NULL,
    InstallDate       date         NOT NULL,
    DecommissionDate  date         NULL
);

IF OBJECT_ID(N'ops.Incident') IS NULL
CREATE TABLE ops.Incident (
    TicketId             varchar(20)  NOT NULL CONSTRAINT PK_ops_Incident PRIMARY KEY,
    CircuitId            varchar(20)  NOT NULL,
    PriorityCode         char(2)      NOT NULL,
    OpenedAt             datetime2(0) NOT NULL,   -- local time, Europe/Madrid
    RestoredAt           datetime2(0) NULL,       -- NULL while the service is down
    ClosedAt             datetime2(0) NULL,
    Status               varchar(10)  NOT NULL,   -- Open, Restored, Closed
    RootCauseCode        varchar(3)   NULL,       -- filled when restored
    ResponsibleTeam      nvarchar(40) NOT NULL,
    IsCancelled          bit          NOT NULL,
    DuplicateOfTicketId  varchar(20)  NULL        -- set when an agent marked the ticket as duplicate
);

IF OBJECT_ID(N'ops.ImprovementAction') IS NULL
CREATE TABLE ops.ImprovementAction (
    ActionId        int          NOT NULL CONSTRAINT PK_ops_ImprovementAction PRIMARY KEY,
    CircuitId       varchar(20)  NOT NULL,
    ActionTypeCode  varchar(15)  NOT NULL,
    StartDate       date         NOT NULL,
    CompletionDate  date         NULL,
    Status          varchar(12)  NOT NULL     -- Planned, In progress, Completed, Cancelled
);
GO
