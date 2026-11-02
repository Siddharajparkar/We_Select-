-- ============================================================================
-- Migration: 0003_jobs_questions_ai.sql  (Phase 6)
-- jobs:      run_after (retry back-off), started_at, tokens_used (AI usage)
-- questions: status (draft|approved), explanation (MCQ/cognitive), word_limit (descriptive)
-- Idempotent: every column is guarded by COL_LENGTH, re-running is a no-op.
-- ============================================================================
IF COL_LENGTH(N'[assess].[jobs]', N'run_after') IS NULL
BEGIN
    ALTER TABLE [assess].[jobs] ADD [run_after] DATETIME2(3) NULL;
END;

IF COL_LENGTH(N'[assess].[jobs]', N'started_at') IS NULL
BEGIN
    ALTER TABLE [assess].[jobs] ADD [started_at] DATETIME2(3) NULL;
END;

IF COL_LENGTH(N'[assess].[jobs]', N'tokens_used') IS NULL
BEGIN
    ALTER TABLE [assess].[jobs]
        ADD [tokens_used] INT NOT NULL CONSTRAINT DF_jobs_tokens_used DEFAULT 0;
END;

IF COL_LENGTH(N'[assess].[questions]', N'status') IS NULL
BEGIN
    ALTER TABLE [assess].[questions]
        ADD [status] NVARCHAR(20) NOT NULL
            CONSTRAINT DF_questions_status DEFAULT N'draft'
            CONSTRAINT CK_questions_status CHECK ([status] IN (N'draft', N'approved'));
END;

IF COL_LENGTH(N'[assess].[questions]', N'explanation') IS NULL
BEGIN
    ALTER TABLE [assess].[questions] ADD [explanation] NVARCHAR(MAX) NULL;
END;

IF COL_LENGTH(N'[assess].[questions]', N'word_limit') IS NULL
BEGIN
    ALTER TABLE [assess].[questions] ADD [word_limit] INT NULL;
END;
