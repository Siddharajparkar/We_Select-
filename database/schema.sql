-- ============================================================
-- We_Select Assessment Portal - Database Schema
-- Azure SQL Database (T-SQL)
-- Created by: M2
-- ============================================================

-- ============================================================
-- 1. TENANTS
-- Companies/organisations using the platform
-- ============================================================
CREATE TABLE tenants (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    name            NVARCHAR(255)   NOT NULL,
    domain          NVARCHAR(255)   NOT NULL UNIQUE,   -- e.g. company.com
    is_active       BIT             NOT NULL DEFAULT 1,
    created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

-- ============================================================
-- 2. USERS
-- Admin / HR accounts (one per tenant)
-- ============================================================
CREATE TABLE users (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id       INT             NOT NULL REFERENCES tenants(id),
    email           NVARCHAR(255)   NOT NULL,
    password_hash   NVARCHAR(255)   NOT NULL,
    full_name       NVARCHAR(255)   NOT NULL,
    role            NVARCHAR(50)    NOT NULL DEFAULT 'admin',  -- admin, hr
    is_active       BIT             NOT NULL DEFAULT 1,
    created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT uq_users_email_tenant UNIQUE (email, tenant_id)
);

-- ============================================================
-- 3. SESSIONS
-- Session-based auth — NO JWT anywhere
-- session_id is stored as HttpOnly cookie on the client
-- ============================================================
CREATE TABLE sessions (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    session_id      NVARCHAR(128)   NOT NULL UNIQUE,  -- random UUID, used as cookie value
    user_id         INT             NOT NULL REFERENCES users(id),
    tenant_id       INT             NOT NULL REFERENCES tenants(id),
    ip_address      NVARCHAR(45)    NULL,
    user_agent      NVARCHAR(500)   NULL,
    created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    expires_at      DATETIME2       NOT NULL
);

-- Index for fast session lookup on every request
CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

-- ============================================================
-- 4. ASSESSMENTS
-- Assessment configurations created by HR/admin
-- ============================================================
CREATE TABLE assessments (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id           INT             NOT NULL REFERENCES tenants(id),
    created_by          INT             NOT NULL REFERENCES users(id),
    title               NVARCHAR(255)   NOT NULL,
    job_description     NVARCHAR(MAX)   NOT NULL,
    domain              NVARCHAR(100)   NOT NULL,   -- e.g. Software Engineering
    difficulty          NVARCHAR(50)    NOT NULL DEFAULT 'medium',  -- easy, medium, hard
    mcq_count           INT             NOT NULL DEFAULT 0,
    descriptive_count   INT             NOT NULL DEFAULT 0,
    cognitive_count     INT             NOT NULL DEFAULT 0,
    time_limit_minutes  INT             NOT NULL DEFAULT 60,
    status              NVARCHAR(50)    NOT NULL DEFAULT 'draft',  -- draft, active, closed
    ai_generation_status NVARCHAR(50)   NOT NULL DEFAULT 'pending', -- pending, processing, done, failed
    created_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    updated_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX idx_assessments_tenant_id ON assessments(tenant_id);
CREATE INDEX idx_assessments_status ON assessments(status);

-- ============================================================
-- 5. QUESTIONS
-- AI-generated questions linked to an assessment
-- ============================================================
CREATE TABLE questions (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id       INT             NOT NULL REFERENCES tenants(id),
    assessment_id   INT             NOT NULL REFERENCES assessments(id),
    question_type   NVARCHAR(50)    NOT NULL,   -- mcq, descriptive, cognitive
    question_text   NVARCHAR(MAX)   NOT NULL,
    options         NVARCHAR(MAX)   NULL,       -- JSON array for MCQ/cognitive: ["A. ...", "B. ..."]
    correct_answer  NVARCHAR(10)    NULL,       -- e.g. "A" for MCQ/cognitive
    explanation     NVARCHAR(MAX)   NULL,       -- for MCQ/cognitive
    rubric          NVARCHAR(MAX)   NULL,       -- for descriptive
    max_score       INT             NOT NULL DEFAULT 10,
    word_limit      INT             NULL,       -- for descriptive only
    order_index     INT             NOT NULL DEFAULT 0,
    created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX idx_questions_assessment_id ON questions(assessment_id);
CREATE INDEX idx_questions_tenant_id ON questions(tenant_id);

-- ============================================================
-- 6. PARTICIPANTS
-- Candidates invited to take an assessment
-- token_hash = SHA-256 hash of the invitation UUID token (NOT JWT)
-- ============================================================
CREATE TABLE participants (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id       INT             NOT NULL REFERENCES tenants(id),
    assessment_id   INT             NOT NULL REFERENCES assessments(id),
    email           NVARCHAR(255)   NOT NULL,
    full_name       NVARCHAR(255)   NOT NULL,
    token_hash      NVARCHAR(64)    NOT NULL UNIQUE,  -- SHA-256 hex of UUID token
    status          NVARCHAR(50)    NOT NULL DEFAULT 'invited',  -- invited, started, completed, expired
    invited_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    started_at      DATETIME2       NULL,
    completed_at    DATETIME2       NULL,
    expires_at      DATETIME2       NOT NULL,
    CONSTRAINT uq_participant_assessment_email UNIQUE (assessment_id, email)
);

CREATE INDEX idx_participants_token_hash ON participants(token_hash);
CREATE INDEX idx_participants_assessment_id ON participants(assessment_id);
CREATE INDEX idx_participants_tenant_id ON participants(tenant_id);

-- ============================================================
-- 7. RESPONSES
-- Candidate answers per question
-- ============================================================
CREATE TABLE responses (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id           INT             NOT NULL REFERENCES tenants(id),
    participant_id      INT             NOT NULL REFERENCES participants(id),
    assessment_id       INT             NOT NULL REFERENCES assessments(id),
    question_id         INT             NOT NULL REFERENCES questions(id),
    answer_text         NVARCHAR(MAX)   NULL,   -- for descriptive answers
    selected_option     NVARCHAR(10)    NULL,   -- e.g. "A" for MCQ/cognitive
    is_correct          BIT             NULL,   -- set after auto-marking MCQ/cognitive
    ai_score            INT             NULL,   -- set by AI evaluator for descriptive
    ai_justification    NVARCHAR(MAX)   NULL,   -- AI explanation of score
    ai_eval_status      NVARCHAR(50)    NOT NULL DEFAULT 'pending',  -- pending, done, failed
    submitted_at        DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT uq_response_participant_question UNIQUE (participant_id, question_id)
);

CREATE INDEX idx_responses_participant_id ON responses(participant_id);
CREATE INDEX idx_responses_assessment_id ON responses(assessment_id);
CREATE INDEX idx_responses_tenant_id ON responses(tenant_id);

-- ============================================================
-- 8. RESULTS
-- Final aggregated scores per participant per assessment
-- ============================================================
CREATE TABLE results (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    tenant_id           INT             NOT NULL REFERENCES tenants(id),
    participant_id      INT             NOT NULL REFERENCES participants(id) UNIQUE,
    assessment_id       INT             NOT NULL REFERENCES assessments(id),
    mcq_score           INT             NOT NULL DEFAULT 0,
    cognitive_score     INT             NOT NULL DEFAULT 0,
    descriptive_score   INT             NOT NULL DEFAULT 0,
    total_score         INT             NOT NULL DEFAULT 0,
    max_possible_score  INT             NOT NULL DEFAULT 0,
    percentage          DECIMAL(5,2)    NOT NULL DEFAULT 0.00,
    status              NVARCHAR(50)    NOT NULL DEFAULT 'pending',  -- pending, evaluated, reviewed
    evaluated_at        DATETIME2       NULL,
    created_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX idx_results_assessment_id ON results(assessment_id);
CREATE INDEX idx_results_tenant_id ON results(tenant_id);

-- ============================================================
-- END OF SCHEMA
-- ============================================================
