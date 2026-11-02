# Assessment Platform Data Model

This document outlines the entity relationships, composite keys, tenant isolation model, and data structures implemented in schema `[assess]` for the AI Candidate Assessment Platform.

---

## 1. Entity-Relationship Diagram (Mermaid)

```mermaid
erDiagram
    tenants ||--o{ users : "has"
    tenants ||--o{ assessments : "owns"
    tenants ||--o{ jobs : "tracks"
    tenants ||--o{ audit_log : "records"

    users ||--o{ sessions : "authenticates"
    users ||--o{ assessments : "creates"

    assessments ||--o{ questions : "contains"
    assessments ||--o{ participants : "invites"
    assessments ||--o{ attempts : "evaluates"

    participants ||--o| attempts : "undertakes"

    attempts ||--o{ responses : "records"
    attempts ||--o{ scores : "graded_by"

    questions ||--o{ responses : "answered_in"
    questions ||--o{ scores : "evaluated_in"

    tenants {
        uniqueidentifier id PK
        nvarchar name
        varchar status
        datetime2 created_at
        datetime2 updated_at
    }

    users {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        nvarchar name
        nvarchar email UK
        varchar password_hash
        varchar role
        varchar status
        datetime2 created_at
        datetime2 updated_at
    }

    sessions {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier user_id FK
        varchar token_hash UK
        datetime2 expires_at
        datetime2 created_at
    }

    login_attempts {
        uniqueidentifier id PK
        nvarchar email
        varchar ip_address
        datetime2 attempted_at
        bit success
    }

    assessments {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        nvarchar title
        nvarchar job_description
        nvarchar jd_file_name
        int duration_minutes
        int passing_score
        varchar status
        nvarchar sections_json
        uniqueidentifier created_by FK
        datetime2 created_at
        datetime2 updated_at
    }

    questions {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier assessment_id FK
        int section_index
        varchar type
        nvarchar body
        nvarchar options_json
        nvarchar correct_answer
        nvarchar rubric
        int max_score
        varchar source
        int position
        datetime2 created_at
        datetime2 updated_at
    }

    participants {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier assessment_id FK
        nvarchar name
        nvarchar email
        varchar invite_status
        varchar token_hash UK_FILTERED
        datetime2 token_expires_at
        datetime2 invited_at
        datetime2 created_at
        datetime2 updated_at
    }

    attempts {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier participant_id FK,UK
        uniqueidentifier assessment_id FK
        varchar attempt_token_hash UK
        datetime2 started_at
        datetime2 deadline_at
        datetime2 submitted_at
        varchar status
        decimal score
        decimal max_score
        decimal percent
        bit passed
        datetime2 created_at
        datetime2 updated_at
    }

    responses {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier attempt_id FK
        uniqueidentifier question_id FK
        nvarchar answer_text
        datetime2 saved_at
    }

    scores {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier attempt_id FK
        uniqueidentifier question_id FK
        decimal score
        decimal max_score
        varchar source
        nvarchar justification
        datetime2 created_at
        datetime2 updated_at
    }

    jobs {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        varchar type
        varchar status
        uniqueidentifier ref_id
        nvarchar payload_json
        nvarchar result_json
        nvarchar error
        int attempts
        int max_attempts
        datetime2 locked_at
        nvarchar locked_by
        datetime2 created_at
        datetime2 updated_at
    }

    audit_log {
        uniqueidentifier id PK
        uniqueidentifier tenant_id FK
        uniqueidentifier actor_id
        varchar action
        varchar entity_type
        uniqueidentifier entity_id
        nvarchar details_json
        datetime2 created_at
    }

    schema_migrations {
        int version PK
        nvarchar name
        datetime2 applied_at
    }
```

---

## 2. Multi-Tenant Architectural Enforcement

1. **Schema Qualification:** All tables and indices reside exclusively within the dedicated `[assess]` schema. The shared `[dbo]` schema is never modified or accessed.
2. **Composite Foreign Keys:** Child entities enforce tenant boundaries at the database engine level via composite foreign keys:
   - `FK_sessions_user`: `(tenant_id, user_id) -> assess.users(tenant_id, id)`
   - `FK_assessments_creator`: `(tenant_id, created_by) -> assess.users(tenant_id, id)`
   - `FK_questions_assessment`: `(tenant_id, assessment_id) -> assess.assessments(tenant_id, id)`
   - `FK_participants_assessment`: `(tenant_id, assessment_id) -> assess.assessments(tenant_id, id)`
   - `FK_attempts_participant`: `(tenant_id, participant_id) -> assess.participants(tenant_id, id)`
   - `FK_attempts_assessment`: `(tenant_id, assessment_id) -> assess.assessments(tenant_id, id)`
   - `FK_responses_attempt`: `(tenant_id, attempt_id) -> assess.attempts(tenant_id, id)`
   - `FK_responses_question`: `(tenant_id, question_id) -> assess.questions(tenant_id, id)`
   - `FK_scores_attempt`: `(tenant_id, attempt_id) -> assess.attempts(tenant_id, id)`
   - `FK_scores_question`: `(tenant_id, question_id) -> assess.questions(tenant_id, id)`
3. **Filtered Unique Indexes:** `participants(token_hash)` allows multiple `NULL` values (uninvited candidates) while strictly guaranteeing uniqueness among non-`NULL` invitation tokens.
4. **JSON Constraints:** `ISJSON(column) = 1` checks protect JSON payloads on `sections_json`, `options_json`, `payload_json`, `result_json`, and `details_json`.
