-- ============================================================================
-- Migration: 0001_init.sql
-- Schema: assess
-- Purpose: Initial baseline schema for AI Candidate Assessment Platform
-- Enforces:
--   - Tenant isolation via tenant_id on all child tables
--   - Composite foreign keys (tenant_id, parent_id)
--   - Filtered index on participants(token_hash)
--   - Check constraints on types, status, and JSON validity
-- ============================================================================

-- 1. Tenants
IF OBJECT_ID(N'[assess].[tenants]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[tenants] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_tenants PRIMARY KEY,
        [name] NVARCHAR(255) NOT NULL,
        [status] VARCHAR(20) NOT NULL CONSTRAINT DF_tenants_status DEFAULT 'active'
            CONSTRAINT CK_tenants_status CHECK ([status] IN ('active', 'suspended')),
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_tenants_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_tenants_updated_at DEFAULT SYSUTCDATETIME()
    );
END;

-- 2. Users (Staff)
IF OBJECT_ID(N'[assess].[users]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[users] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_users PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT FK_users_tenant REFERENCES [assess].[tenants]([id]),
        [name] NVARCHAR(255) NOT NULL,
        [email] NVARCHAR(320) NOT NULL,
        [password_hash] VARCHAR(255) NOT NULL,
        [role] VARCHAR(20) NOT NULL
            CONSTRAINT CK_users_role CHECK ([role] IN ('admin', 'recruiter', 'reviewer')),
        [status] VARCHAR(20) NOT NULL CONSTRAINT DF_users_status DEFAULT 'active'
            CONSTRAINT CK_users_status CHECK ([status] IN ('active', 'disabled')),
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_users_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_users_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_users_tenant_email UNIQUE ([tenant_id], [email]),
        CONSTRAINT UQ_users_email UNIQUE ([email]),
        CONSTRAINT UQ_users_tenant_id UNIQUE ([tenant_id], [id])
    );
END;

-- 3. Sessions
IF OBJECT_ID(N'[assess].[sessions]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[sessions] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_sessions PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL,
        [user_id] UNIQUEIDENTIFIER NOT NULL,
        [token_hash] VARCHAR(64) NOT NULL CONSTRAINT UQ_sessions_token_hash UNIQUE,
        [expires_at] DATETIME2(3) NOT NULL,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_sessions_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_sessions_user FOREIGN KEY ([tenant_id], [user_id])
            REFERENCES [assess].[users]([tenant_id], [id]) ON DELETE CASCADE
    );
    CREATE INDEX IX_sessions_user_id ON [assess].[sessions]([user_id]);
END;

-- 4. Login Attempts
IF OBJECT_ID(N'[assess].[login_attempts]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[login_attempts] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_login_attempts PRIMARY KEY,
        [email] NVARCHAR(320) NOT NULL,
        [ip_address] VARCHAR(45) NOT NULL,
        [attempted_at] DATETIME2(3) NOT NULL CONSTRAINT DF_login_attempts_attempted_at DEFAULT SYSUTCDATETIME(),
        [success] BIT NOT NULL
    );
    CREATE INDEX IX_login_attempts_email ON [assess].[login_attempts]([email], [attempted_at] DESC);
END;

-- 5. Assessments
IF OBJECT_ID(N'[assess].[assessments]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[assessments] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_assessments PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT FK_assessments_tenant REFERENCES [assess].[tenants]([id]),
        [title] NVARCHAR(255) NOT NULL,
        [job_description] NVARCHAR(MAX) NULL,
        [jd_file_name] NVARCHAR(255) NULL,
        [duration_minutes] INT NOT NULL CONSTRAINT DF_assessments_duration DEFAULT 60
            CONSTRAINT CK_assessments_duration CHECK ([duration_minutes] BETWEEN 5 AND 240),
        [passing_score] INT NOT NULL CONSTRAINT DF_assessments_passing_score DEFAULT 60
            CONSTRAINT CK_assessments_passing_score CHECK ([passing_score] BETWEEN 0 AND 100),
        [status] VARCHAR(20) NOT NULL CONSTRAINT DF_assessments_status DEFAULT 'draft'
            CONSTRAINT CK_assessments_status CHECK ([status] IN ('draft', 'approved', 'open', 'closed')),
        [sections_json] NVARCHAR(MAX) NOT NULL
            CONSTRAINT CK_assessments_sections_json CHECK (ISJSON([sections_json]) = 1),
        [created_by] UNIQUEIDENTIFIER NOT NULL,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_assessments_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_assessments_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_assessments_tenant_id UNIQUE ([tenant_id], [id]),
        CONSTRAINT FK_assessments_creator FOREIGN KEY ([tenant_id], [created_by])
            REFERENCES [assess].[users]([tenant_id], [id])
    );
    CREATE INDEX IX_assessments_tenant_status ON [assess].[assessments]([tenant_id], [status]);
END;

-- 6. Questions
IF OBJECT_ID(N'[assess].[questions]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[questions] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_questions PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL,
        [assessment_id] UNIQUEIDENTIFIER NOT NULL,
        [section_index] INT NOT NULL CONSTRAINT DF_questions_section_index DEFAULT 0,
        [type] VARCHAR(20) NOT NULL
            CONSTRAINT CK_questions_type CHECK ([type] IN ('mcq', 'descriptive', 'cognitive')),
        [body] NVARCHAR(MAX) NOT NULL,
        [options_json] NVARCHAR(MAX) NULL
            CONSTRAINT CK_questions_options_json CHECK ([options_json] IS NULL OR ISJSON([options_json]) = 1),
        [correct_answer] NVARCHAR(MAX) NULL,
        [rubric] NVARCHAR(MAX) NULL,
        [max_score] INT NOT NULL CONSTRAINT DF_questions_max_score DEFAULT 10
            CONSTRAINT CK_questions_max_score CHECK ([max_score] BETWEEN 1 AND 20),
        [source] VARCHAR(20) NOT NULL CONSTRAINT DF_questions_source DEFAULT 'ai'
            CONSTRAINT CK_questions_source CHECK ([source] IN ('ai', 'custom')),
        [position] INT NOT NULL CONSTRAINT DF_questions_position DEFAULT 0,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_questions_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_questions_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_questions_tenant_id UNIQUE ([tenant_id], [id]),
        CONSTRAINT FK_questions_assessment FOREIGN KEY ([tenant_id], [assessment_id])
            REFERENCES [assess].[assessments]([tenant_id], [id]) ON DELETE CASCADE
    );
    CREATE INDEX IX_questions_assessment ON [assess].[questions]([tenant_id], [assessment_id], [position]);
END;

-- 7. Participants (Candidates)
IF OBJECT_ID(N'[assess].[participants]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[participants] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_participants PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL,
        [assessment_id] UNIQUEIDENTIFIER NOT NULL,
        [name] NVARCHAR(255) NOT NULL,
        [email] NVARCHAR(320) NOT NULL,
        [invite_status] VARCHAR(20) NOT NULL CONSTRAINT DF_participants_invite_status DEFAULT 'none'
            CONSTRAINT CK_participants_invite_status CHECK ([invite_status] IN ('none', 'queued', 'sent', 'failed')),
        [token_hash] VARCHAR(64) NULL,
        [token_expires_at] DATETIME2(3) NULL,
        [invited_at] DATETIME2(3) NULL,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_participants_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_participants_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_participants_tenant_id UNIQUE ([tenant_id], [id]),
        CONSTRAINT UQ_participants_assessment_email UNIQUE ([tenant_id], [assessment_id], [email]),
        CONSTRAINT FK_participants_assessment FOREIGN KEY ([tenant_id], [assessment_id])
            REFERENCES [assess].[assessments]([tenant_id], [id]) ON DELETE CASCADE
    );
END;

-- Filtered unique index on token_hash (NULL values may repeat)
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_participants_token_hash' AND object_id = OBJECT_ID(N'[assess].[participants]')
)
BEGIN
    CREATE UNIQUE INDEX UQ_participants_token_hash
        ON [assess].[participants]([token_hash])
        WHERE [token_hash] IS NOT NULL;
END;

-- 8. Attempts
IF OBJECT_ID(N'[assess].[attempts]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[attempts] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_attempts PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL,
        [participant_id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT UQ_attempts_participant UNIQUE,
        [assessment_id] UNIQUEIDENTIFIER NOT NULL,
        [attempt_token_hash] VARCHAR(64) NOT NULL CONSTRAINT UQ_attempts_token_hash UNIQUE,
        [started_at] DATETIME2(3) NOT NULL CONSTRAINT DF_attempts_started_at DEFAULT SYSUTCDATETIME(),
        [deadline_at] DATETIME2(3) NOT NULL,
        [submitted_at] DATETIME2(3) NULL,
        [status] VARCHAR(20) NOT NULL CONSTRAINT DF_attempts_status DEFAULT 'in_progress'
            CONSTRAINT CK_attempts_status CHECK ([status] IN ('in_progress', 'submitted', 'scored', 'needs_review')),
        [score] DECIMAL(5,2) NULL,
        [max_score] DECIMAL(5,2) NULL,
        [percent] DECIMAL(5,2) NULL,
        [passed] BIT NULL,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_attempts_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_attempts_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_attempts_tenant_id UNIQUE ([tenant_id], [id]),
        CONSTRAINT FK_attempts_participant FOREIGN KEY ([tenant_id], [participant_id])
            REFERENCES [assess].[participants]([tenant_id], [id]),
        CONSTRAINT FK_attempts_assessment FOREIGN KEY ([tenant_id], [assessment_id])
            REFERENCES [assess].[assessments]([tenant_id], [id])
    );
    CREATE INDEX IX_attempts_assessment_status ON [assess].[attempts]([tenant_id], [assessment_id], [status]);
END;

-- 9. Responses
IF OBJECT_ID(N'[assess].[responses]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[responses] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_responses PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL,
        [attempt_id] UNIQUEIDENTIFIER NOT NULL,
        [question_id] UNIQUEIDENTIFIER NOT NULL,
        [answer_text] NVARCHAR(MAX) NULL,
        [saved_at] DATETIME2(3) NOT NULL CONSTRAINT DF_responses_saved_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_responses_tenant_id UNIQUE ([tenant_id], [id]),
        CONSTRAINT UQ_responses_attempt_question UNIQUE ([attempt_id], [question_id]),
        CONSTRAINT FK_responses_attempt FOREIGN KEY ([tenant_id], [attempt_id])
            REFERENCES [assess].[attempts]([tenant_id], [id]) ON DELETE CASCADE,
        CONSTRAINT FK_responses_question FOREIGN KEY ([tenant_id], [question_id])
            REFERENCES [assess].[questions]([tenant_id], [id])
    );
END;

-- 10. Scores
IF OBJECT_ID(N'[assess].[scores]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[scores] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_scores PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL,
        [attempt_id] UNIQUEIDENTIFIER NOT NULL,
        [question_id] UNIQUEIDENTIFIER NOT NULL,
        [score] DECIMAL(5,2) NOT NULL,
        [max_score] DECIMAL(5,2) NOT NULL,
        [source] VARCHAR(20) NOT NULL
            CONSTRAINT CK_scores_source CHECK ([source] IN ('auto', 'ai', 'manual')),
        [justification] NVARCHAR(MAX) NULL,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_scores_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_scores_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_scores_tenant_id UNIQUE ([tenant_id], [id]),
        CONSTRAINT UQ_scores_attempt_question UNIQUE ([attempt_id], [question_id]),
        CONSTRAINT FK_scores_attempt FOREIGN KEY ([tenant_id], [attempt_id])
            REFERENCES [assess].[attempts]([tenant_id], [id]) ON DELETE CASCADE,
        CONSTRAINT FK_scores_question FOREIGN KEY ([tenant_id], [question_id])
            REFERENCES [assess].[questions]([tenant_id], [id])
    );
END;

-- 11. Jobs
IF OBJECT_ID(N'[assess].[jobs]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[jobs] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_jobs PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT FK_jobs_tenant REFERENCES [assess].[tenants]([id]),
        [type] VARCHAR(20) NOT NULL
            CONSTRAINT CK_jobs_type CHECK ([type] IN ('generate', 'mark', 'email')),
        [status] VARCHAR(20) NOT NULL CONSTRAINT DF_jobs_status DEFAULT 'queued'
            CONSTRAINT CK_jobs_status CHECK ([status] IN ('queued', 'running', 'done', 'failed')),
        [ref_id] UNIQUEIDENTIFIER NOT NULL,
        [payload_json] NVARCHAR(MAX) NOT NULL
            CONSTRAINT CK_jobs_payload_json CHECK (ISJSON([payload_json]) = 1),
        [result_json] NVARCHAR(MAX) NULL
            CONSTRAINT CK_jobs_result_json CHECK ([result_json] IS NULL OR ISJSON([result_json]) = 1),
        [error] NVARCHAR(MAX) NULL,
        [attempts] INT NOT NULL CONSTRAINT DF_jobs_attempts DEFAULT 0,
        [max_attempts] INT NOT NULL CONSTRAINT DF_jobs_max_attempts DEFAULT 3,
        [locked_at] DATETIME2(3) NULL,
        [locked_by] NVARCHAR(100) NULL,
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_jobs_created_at DEFAULT SYSUTCDATETIME(),
        [updated_at] DATETIME2(3) NOT NULL CONSTRAINT DF_jobs_updated_at DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_jobs_claim ON [assess].[jobs]([status], [created_at]);
END;

-- 12. Audit Log
IF OBJECT_ID(N'[assess].[audit_log]', N'U') IS NULL
BEGIN
    CREATE TABLE [assess].[audit_log] (
        [id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_audit_log PRIMARY KEY,
        [tenant_id] UNIQUEIDENTIFIER NOT NULL CONSTRAINT FK_audit_log_tenant REFERENCES [assess].[tenants]([id]),
        [actor_id] UNIQUEIDENTIFIER NULL,
        [action] VARCHAR(50) NOT NULL,
        [entity_type] VARCHAR(50) NOT NULL,
        [entity_id] UNIQUEIDENTIFIER NOT NULL,
        [details_json] NVARCHAR(MAX) NULL
            CONSTRAINT CK_audit_log_details_json CHECK ([details_json] IS NULL OR ISJSON([details_json]) = 1),
        [created_at] DATETIME2(3) NOT NULL CONSTRAINT DF_audit_log_created_at DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_audit_log_tenant_entity ON [assess].[audit_log]([tenant_id], [entity_type], [entity_id]);
END;
