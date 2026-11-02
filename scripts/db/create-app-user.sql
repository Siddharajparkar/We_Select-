-- scripts/db/create-app-user.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- Run ONCE in the Azure Portal Query Editor (org laptop, OC-1B).
-- Creates the assess schema and the app user that owns ONLY that schema.
-- The app user has NO access to dbo tables (existing portal tables are safe).
--
-- IMPORTANT: Replace all <placeholders> with real values in Cloud Shell
-- (the real values are never committed to the repository).
--
-- Run as: the SQL server admin (the one that created the database).
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Create the dedicated schema
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'assess')
BEGIN
    EXEC('CREATE SCHEMA [assess] AUTHORIZATION [dbo]');
    PRINT 'Schema [assess] created.';
END
ELSE
BEGIN
    PRINT 'Schema [assess] already exists.';
END;

-- 2. Create the contained database user (SQL auth)
--    Replace <APP_USER_PASSWORD> with the value generated in OC-1F.
--    NEVER commit this file with a real password.
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'assess_app')
BEGIN
    CREATE USER [assess_app] WITH PASSWORD = '<APP_USER_PASSWORD>';
    PRINT 'User [assess_app] created.';
END
ELSE
BEGIN
    PRINT 'User [assess_app] already exists.';
END;

-- 3. Transfer ownership of the assess schema to the app user
ALTER AUTHORIZATION ON SCHEMA::[assess] TO [assess_app];
PRINT 'Schema [assess] ownership transferred to [assess_app].';

-- 4. Grant CREATE TABLE inside the assess schema (needed for migrations)
GRANT CREATE TABLE TO [assess_app];
PRINT 'GRANT CREATE TABLE to [assess_app].';

-- 5. SAFETY: verify the user cannot touch dbo tables
--    This check will fail if assess_app somehow got db_datareader or db_datawriter.
--    If this block fails, the setup is wrong — stop and fix.
IF IS_MEMBER('db_datareader') = 1 OR IS_MEMBER('db_datawriter') = 1
   OR IS_MEMBER('db_ddladmin') = 1
BEGIN
    PRINT 'WARNING: assess_app is in a broad role (db_datareader/writer/ddladmin).';
    PRINT 'Remove it from those roles before continuing.';
    -- Do NOT RAISERROR here — just warn; the probe tool will confirm.
END

-- 6. Print summary
PRINT '';
PRINT '=== assess schema and app user setup complete ===';
PRINT 'User:   assess_app';
PRINT 'Schema: assess (owned by assess_app)';
PRINT 'Roles:  none (no db_datareader, db_datawriter, db_ddladmin)';
PRINT 'Next:   Run migrations with REPO_BACKEND=sql (OC-2)';
PRINT '        Then run probe sql to confirm (OC-1H)';
