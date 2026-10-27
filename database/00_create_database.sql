/*
    NorthGrid Telecom (fictional) - B2B Network Operations Intelligence
    Step 00: database and schemas. Safe to run more than once.

    cfg  KPI parameters the operations committee can change
    ref  reference data: regions, technologies, tiers, priorities, SLA targets, root causes
    ops  operational source tables: customers, circuits, incidents, improvement actions
    dw   dimensional model (star schema) read by Power BI
    dq   data quality checks
*/
IF DB_ID(N'NorthGridOps') IS NULL
    CREATE DATABASE NorthGridOps;
GO

USE NorthGridOps;
GO

IF SCHEMA_ID(N'cfg') IS NULL EXEC (N'CREATE SCHEMA cfg');
IF SCHEMA_ID(N'ref') IS NULL EXEC (N'CREATE SCHEMA ref');
IF SCHEMA_ID(N'ops') IS NULL EXEC (N'CREATE SCHEMA ops');
IF SCHEMA_ID(N'dw')  IS NULL EXEC (N'CREATE SCHEMA dw');
IF SCHEMA_ID(N'dq')  IS NULL EXEC (N'CREATE SCHEMA dq');
GO
