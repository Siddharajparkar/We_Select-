-- infra/azure/discovery/sql-inventory.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- READ-ONLY T-SQL discovery for the existing Azure SQL database.
-- Run in the Azure Portal Query Editor (org laptop, no install needed).
-- Phase 1 Stage 1 — OC-0 (SQL portion).
--
-- CONSTRAINTS:
--   SELECT-only. No INSERT, UPDATE, DELETE, DROP, CREATE, EXEC, or xp_ calls.
--   No row data is read. Only metadata/catalog views are used.
-- ─────────────────────────────────────────────────────────────────────────────

PRINT '=== DATABASE IDENTITY ===';
SELECT
    DB_NAME()                                       AS database_name,
    SERVERPROPERTY('ServerName')                    AS server_name,
    DATABASEPROPERTYEX(DB_NAME(), 'Collation')      AS collation,
    DATABASEPROPERTYEX(DB_NAME(), 'CompatibilityLevel') AS compatibility_level,
    DATABASEPROPERTYEX(DB_NAME(), 'Edition')        AS edition,
    DATABASEPROPERTYEX(DB_NAME(), 'ServiceObjective') AS service_tier;

PRINT '';
PRINT '=== SCHEMAS (all, including assess if it exists) ===';
SELECT
    s.name          AS schema_name,
    p.name          AS owner,
    s.schema_id
FROM sys.schemas s
JOIN sys.database_principals p ON s.principal_id = p.principal_id
ORDER BY s.schema_id;

PRINT '';
PRINT '=== TABLE COUNTS PER SCHEMA ===';
SELECT
    s.name          AS schema_name,
    COUNT(*)        AS table_count
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
WHERE t.is_ms_shipped = 0
GROUP BY s.name
ORDER BY s.name;

PRINT '';
PRINT '=== TABLE LIST (schema, name, column count only — no row data) ===';
SELECT
    s.name                  AS schema_name,
    t.name                  AS table_name,
    COUNT(c.column_id)      AS column_count,
    t.create_date           AS created_at
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
JOIN sys.columns c ON c.object_id = t.object_id
WHERE t.is_ms_shipped = 0
GROUP BY s.name, t.name, t.create_date
ORDER BY s.name, t.name;

PRINT '';
PRINT '=== INDEX LIST (schema, table, index name, type, uniqueness, filtration) ===';
SELECT
    s.name              AS schema_name,
    t.name              AS table_name,
    i.name              AS index_name,
    i.type_desc         AS index_type,
    i.is_unique         AS is_unique,
    i.has_filter        AS is_filtered,
    i.filter_definition AS filter_expr
FROM sys.indexes i
JOIN sys.tables t ON i.object_id = t.object_id
JOIN sys.schemas s ON t.schema_id = s.schema_id
WHERE t.is_ms_shipped = 0
  AND i.type > 0
ORDER BY s.name, t.name, i.name;

PRINT '';
PRINT '=== DATABASE USERS AND ROLES ===';
SELECT
    p.name              AS principal_name,
    p.type_desc         AS principal_type,
    p.default_schema_name AS default_schema,
    p.create_date
FROM sys.database_principals p
WHERE p.type IN ('S', 'U', 'G', 'R')
  AND p.name NOT IN ('dbo', 'guest', 'INFORMATION_SCHEMA', 'sys',
                     'db_owner', 'db_accessadmin', 'db_securityadmin',
                     'db_ddladmin', 'db_backupoperator', 'db_datareader',
                     'db_datawriter', 'db_denydatareader', 'db_denydatawriter')
ORDER BY p.type, p.name;

PRINT '';
PRINT '=== ROLE MEMBERSHIPS ===';
SELECT
    r.name              AS role_name,
    m.name              AS member_name
FROM sys.database_role_members rm
JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
ORDER BY r.name, m.name;

PRINT '';
PRINT '=== SCHEMA PERMISSIONS ===';
SELECT
    pe.state_desc       AS permission_state,
    pe.permission_name,
    SCHEMA_NAME(pe.major_id) AS schema_name,
    p.name              AS grantee
FROM sys.database_permissions pe
JOIN sys.database_principals p ON pe.grantee_principal_id = p.principal_id
WHERE pe.class_desc = 'SCHEMA'
ORDER BY schema_name, grantee;

PRINT '';
PRINT '=== EXISTING MIGRATION TABLE (if any) ===';
SELECT
    CASE WHEN OBJECT_ID('[assess].[schema_migrations]') IS NOT NULL
         THEN 'EXISTS in assess schema'
         WHEN OBJECT_ID('[dbo].[schema_migrations]') IS NOT NULL
         THEN 'EXISTS in dbo schema'
         ELSE 'NOT FOUND'
    END AS schema_migrations_status;

PRINT '';
PRINT '=== DISCOVERY COMPLETE ===';
PRINT 'Copy and paste this output into: office report OC-0 (SQL section).';
PRINT 'No secrets or row data were read.';
