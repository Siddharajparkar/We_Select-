-- ============================================================================
-- Migration: 0002_sessions_last_seen.sql  (Phase 4)
-- Adds sessions.last_seen_at so idle expiry (30 min) can be enforced.
-- Idempotent: re-running is a no-op.
-- ============================================================================
IF COL_LENGTH(N'[assess].[sessions]', N'last_seen_at') IS NULL
BEGIN
    ALTER TABLE [assess].[sessions]
        ADD [last_seen_at] DATETIME2(3) NOT NULL
            CONSTRAINT DF_sessions_last_seen_at DEFAULT SYSUTCDATETIME();
END;
