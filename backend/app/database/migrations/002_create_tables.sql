-- Migration 002: normalized application tables.
-- Rule enforced by design: PostgreSQL stores the latest approved/current output only.
-- Regeneration attempts, rejected draft payloads, and user story version history
-- belong in Redis, not these tables.

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email CITEXT NOT NULL UNIQUE,
    full_name VARCHAR(160) NOT NULL,
    role VARCHAR(80) NOT NULL DEFAULT 'business_analyst',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT users_email_not_blank CHECK (length(trim(email::text)) > 3),
    CONSTRAINT users_full_name_not_blank CHECK (length(trim(full_name)) > 0)
);

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    name VARCHAR(220) NOT NULL,
    description TEXT,
    status project_status NOT NULL DEFAULT 'active',
    confidence_threshold NUMERIC(5,4) NOT NULL DEFAULT 0.8500,
    max_regeneration_attempts SMALLINT NOT NULL DEFAULT 3,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT projects_name_not_blank CHECK (length(trim(name)) > 0),
    CONSTRAINT projects_confidence_threshold_range CHECK (confidence_threshold >= 0 AND confidence_threshold <= 1),
    CONSTRAINT projects_max_attempts_range CHECK (max_regeneration_attempts BETWEEN 1 AND 10)
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    uploaded_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    original_filename VARCHAR(500) NOT NULL,
    storage_uri TEXT NOT NULL,
    mime_type VARCHAR(160) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 CHAR(64) NOT NULL,
    status document_status NOT NULL DEFAULT 'uploaded',
    parsed_text_hash CHAR(64),
    parser_name VARCHAR(120),
    parser_version VARCHAR(80),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT documents_file_size_positive CHECK (file_size_bytes > 0),
    CONSTRAINT documents_filename_not_blank CHECK (length(trim(original_filename)) > 0),
    CONSTRAINT documents_checksum_hex CHECK (checksum_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT documents_parsed_hash_hex CHECK (parsed_text_hash IS NULL OR parsed_text_hash ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_title TEXT,
    content TEXT NOT NULL,
    token_count INTEGER,
    content_hash CHAR(64) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT document_chunks_index_nonnegative CHECK (chunk_index >= 0),
    CONSTRAINT document_chunks_content_not_blank CHECK (length(trim(content)) > 0),
    CONSTRAINT document_chunks_token_count_nonnegative CHECK (token_count IS NULL OR token_count >= 0),
    CONSTRAINT document_chunks_content_hash_hex CHECK (content_hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT document_chunks_unique_index UNIQUE (document_id, chunk_index),
    CONSTRAINT document_chunks_unique_hash UNIQUE (document_id, content_hash)
);

CREATE TABLE IF NOT EXISTS requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    requirement_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    requirement_type VARCHAR(80) NOT NULL DEFAULT 'functional',
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT requirements_code_not_blank CHECK (length(trim(requirement_code)) > 0),
    CONSTRAINT requirements_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT requirements_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT requirements_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT requirements_unique_code_per_document UNIQUE (document_id, requirement_code)
);

CREATE TABLE IF NOT EXISTS actors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    actor_name VARCHAR(180) NOT NULL,
    actor_type VARCHAR(80) NOT NULL DEFAULT 'external',
    description TEXT,
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT actors_name_not_blank CHECK (length(trim(actor_name)) > 0),
    CONSTRAINT actors_type_not_blank CHECK (length(trim(actor_type)) > 0),
    CONSTRAINT actors_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT actors_unique_name_per_document UNIQUE (document_id, actor_name)
);

CREATE TABLE IF NOT EXISTS functional_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id UUID NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    requirement_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    classification_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT functional_requirements_requirement_unique UNIQUE (requirement_id),
    CONSTRAINT functional_requirements_code_not_blank CHECK (length(trim(requirement_code)) > 0),
    CONSTRAINT functional_requirements_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT functional_requirements_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT functional_requirements_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT functional_requirements_unique_code_per_document UNIQUE (document_id, requirement_code)
);

CREATE TABLE IF NOT EXISTS non_functional_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id UUID NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    requirement_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    quality_attribute VARCHAR(120),
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    classification_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT non_functional_requirements_requirement_unique UNIQUE (requirement_id),
    CONSTRAINT non_functional_requirements_code_not_blank CHECK (length(trim(requirement_code)) > 0),
    CONSTRAINT non_functional_requirements_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT non_functional_requirements_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT non_functional_requirements_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT non_functional_requirements_unique_code_per_document UNIQUE (document_id, requirement_code)
);

CREATE TABLE IF NOT EXISTS business_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    rule_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    rule_type VARCHAR(80) NOT NULL DEFAULT 'business',
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT business_rules_code_not_blank CHECK (length(trim(rule_code)) > 0),
    CONSTRAINT business_rules_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT business_rules_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT business_rules_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT business_rules_unique_code_per_document UNIQUE (document_id, rule_code)
);

CREATE TABLE IF NOT EXISTS dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    source_requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    depends_on_requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    epic_id UUID,
    feature_id UUID,
    user_story_id UUID,
    dependency_code VARCHAR(80) NOT NULL,
    dependency_name VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    dependency_type VARCHAR(80) NOT NULL DEFAULT 'external',
    status VARCHAR(80) NOT NULL DEFAULT 'identified',
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT dependencies_code_not_blank CHECK (length(trim(dependency_code)) > 0),
    CONSTRAINT dependencies_name_not_blank CHECK (length(trim(dependency_name)) > 0),
    CONSTRAINT dependencies_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT dependencies_type_not_blank CHECK (length(trim(dependency_type)) > 0),
    CONSTRAINT dependencies_status_not_blank CHECK (length(trim(status)) > 0),
    CONSTRAINT dependencies_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT dependencies_unique_code_per_document UNIQUE (document_id, dependency_code)
);

CREATE TABLE IF NOT EXISTS business_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    goal_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT business_goals_code_not_blank CHECK (length(trim(goal_code)) > 0),
    CONSTRAINT business_goals_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT business_goals_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT business_goals_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT business_goals_unique_code_per_document UNIQUE (document_id, goal_code)
);

CREATE TABLE IF NOT EXISTS edge_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    edge_case_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    expected_behavior TEXT,
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT edge_cases_code_not_blank CHECK (length(trim(edge_case_code)) > 0),
    CONSTRAINT edge_cases_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT edge_cases_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT edge_cases_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT edge_cases_unique_code_per_document UNIQUE (document_id, edge_case_code)
);

CREATE TABLE IF NOT EXISTS constraints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    constraint_code VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT NOT NULL,
    constraint_type VARCHAR(80) NOT NULL DEFAULT 'business',
    source_reference TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT constraints_code_not_blank CHECK (length(trim(constraint_code)) > 0),
    CONSTRAINT constraints_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT constraints_description_not_blank CHECK (length(trim(description)) > 0),
    CONSTRAINT constraints_type_not_blank CHECK (length(trim(constraint_type)) > 0),
    CONSTRAINT constraints_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT constraints_unique_code_per_document UNIQUE (document_id, constraint_code)
);

CREATE OR REPLACE FUNCTION sync_requirement_classification_tables()
RETURNS TRIGGER AS $$
DECLARE
    normalized_type TEXT;
BEGIN
    normalized_type := lower(replace(replace(trim(NEW.requirement_type), '-', '_'), ' ', '_'));

    IF normalized_type = 'functional' OR normalized_type = 'fr' THEN
        INSERT INTO functional_requirements (
            requirement_id,
            project_id,
            document_id,
            source_chunk_id,
            requirement_code,
            title,
            description,
            priority,
            source_reference,
            confidence_score,
            metadata,
            created_at,
            updated_at,
            deleted_at
        )
        VALUES (
            NEW.id,
            NEW.project_id,
            NEW.document_id,
            NEW.source_chunk_id,
            NEW.requirement_code,
            NEW.title,
            NEW.description,
            NEW.priority,
            NEW.source_reference,
            NEW.confidence_score,
            NEW.metadata,
            NEW.created_at,
            NEW.updated_at,
            NEW.deleted_at
        )
        ON CONFLICT (requirement_id) DO UPDATE SET
            project_id = EXCLUDED.project_id,
            document_id = EXCLUDED.document_id,
            source_chunk_id = EXCLUDED.source_chunk_id,
            requirement_code = EXCLUDED.requirement_code,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            priority = EXCLUDED.priority,
            source_reference = EXCLUDED.source_reference,
            confidence_score = EXCLUDED.confidence_score,
            metadata = EXCLUDED.metadata,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at;

        DELETE FROM non_functional_requirements WHERE requirement_id = NEW.id;
    ELSIF normalized_type IN ('non_functional', 'nonfunctional', 'nfr') THEN
        INSERT INTO non_functional_requirements (
            requirement_id,
            project_id,
            document_id,
            source_chunk_id,
            requirement_code,
            title,
            description,
            priority,
            source_reference,
            confidence_score,
            metadata,
            created_at,
            updated_at,
            deleted_at
        )
        VALUES (
            NEW.id,
            NEW.project_id,
            NEW.document_id,
            NEW.source_chunk_id,
            NEW.requirement_code,
            NEW.title,
            NEW.description,
            NEW.priority,
            NEW.source_reference,
            NEW.confidence_score,
            NEW.metadata,
            NEW.created_at,
            NEW.updated_at,
            NEW.deleted_at
        )
        ON CONFLICT (requirement_id) DO UPDATE SET
            project_id = EXCLUDED.project_id,
            document_id = EXCLUDED.document_id,
            source_chunk_id = EXCLUDED.source_chunk_id,
            requirement_code = EXCLUDED.requirement_code,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            priority = EXCLUDED.priority,
            source_reference = EXCLUDED.source_reference,
            confidence_score = EXCLUDED.confidence_score,
            metadata = EXCLUDED.metadata,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at;

        DELETE FROM functional_requirements WHERE requirement_id = NEW.id;
    ELSE
        DELETE FROM functional_requirements WHERE requirement_id = NEW.id;
        DELETE FROM non_functional_requirements WHERE requirement_id = NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_requirements_sync_classification ON requirements;
CREATE TRIGGER trg_requirements_sync_classification
AFTER INSERT OR UPDATE OF
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    requirement_type,
    priority,
    source_reference,
    confidence_score,
    metadata,
    updated_at,
    deleted_at
ON requirements
FOR EACH ROW
EXECUTE FUNCTION sync_requirement_classification_tables();

INSERT INTO functional_requirements (
    requirement_id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    priority,
    source_reference,
    confidence_score,
    metadata,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    priority,
    source_reference,
    confidence_score,
    metadata,
    created_at,
    updated_at,
    deleted_at
FROM requirements
WHERE lower(replace(replace(trim(requirement_type), '-', '_'), ' ', '_')) IN ('functional', 'fr')
ON CONFLICT (requirement_id) DO UPDATE SET
    project_id = EXCLUDED.project_id,
    document_id = EXCLUDED.document_id,
    source_chunk_id = EXCLUDED.source_chunk_id,
    requirement_code = EXCLUDED.requirement_code,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    priority = EXCLUDED.priority,
    source_reference = EXCLUDED.source_reference,
    confidence_score = EXCLUDED.confidence_score,
    metadata = EXCLUDED.metadata,
    updated_at = EXCLUDED.updated_at,
    deleted_at = EXCLUDED.deleted_at;

INSERT INTO non_functional_requirements (
    requirement_id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    priority,
    source_reference,
    confidence_score,
    metadata,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    priority,
    source_reference,
    confidence_score,
    metadata,
    created_at,
    updated_at,
    deleted_at
FROM requirements
WHERE lower(replace(replace(trim(requirement_type), '-', '_'), ' ', '_')) IN ('non_functional', 'nonfunctional', 'nfr')
ON CONFLICT (requirement_id) DO UPDATE SET
    project_id = EXCLUDED.project_id,
    document_id = EXCLUDED.document_id,
    source_chunk_id = EXCLUDED.source_chunk_id,
    requirement_code = EXCLUDED.requirement_code,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    priority = EXCLUDED.priority,
    source_reference = EXCLUDED.source_reference,
    confidence_score = EXCLUDED.confidence_score,
    metadata = EXCLUDED.metadata,
    updated_at = EXCLUDED.updated_at,
    deleted_at = EXCLUDED.deleted_at;

CREATE TABLE IF NOT EXISTS epics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    epic_key VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT,
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    one_line_story TEXT,
    business_value TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    current_version INTEGER NOT NULL DEFAULT 1,
    feedback TEXT,
    approval_feedback TEXT,
    approval_comments TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT epics_key_not_blank CHECK (length(trim(epic_key)) > 0),
    CONSTRAINT epics_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT epics_description_not_blank CHECK (description IS NULL OR length(trim(description)) > 0),
    CONSTRAINT epics_current_version_positive CHECK (current_version > 0),
    CONSTRAINT epics_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0)),
    CONSTRAINT epics_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT epics_unique_key_per_project UNIQUE (project_id, epic_key)
);

CREATE TABLE IF NOT EXISTS features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    epic_id UUID NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    feature_key VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT,
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    sort_order INTEGER NOT NULL DEFAULT 0,
    current_version INTEGER NOT NULL DEFAULT 1,
    feedback TEXT,
    approval_feedback TEXT,
    approval_comments TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT features_key_not_blank CHECK (length(trim(feature_key)) > 0),
    CONSTRAINT features_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT features_description_not_blank CHECK (description IS NULL OR length(trim(description)) > 0),
    CONSTRAINT features_current_version_positive CHECK (current_version > 0),
    CONSTRAINT features_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0)),
    CONSTRAINT features_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT features_unique_key_per_project UNIQUE (project_id, feature_key)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dependencies_epic_fk') THEN
        ALTER TABLE dependencies
            ADD CONSTRAINT dependencies_epic_fk FOREIGN KEY (epic_id) REFERENCES epics(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dependencies_feature_fk') THEN
        ALTER TABLE dependencies
            ADD CONSTRAINT dependencies_feature_fk FOREIGN KEY (feature_id) REFERENCES features(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS user_stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    feature_id UUID NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    story_key VARCHAR(80) NOT NULL,
    title VARCHAR(260) NOT NULL,
    description TEXT,
    user_role VARCHAR(160) NOT NULL,
    goal TEXT NOT NULL,
    benefit TEXT NOT NULL,
    story_text TEXT NOT NULL,
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    story_points NUMERIC(5,2),
    sort_order INTEGER NOT NULL DEFAULT 0,
    current_version INTEGER NOT NULL DEFAULT 1,
    feedback TEXT,
    approval_feedback TEXT,
    approval_comments TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT user_stories_key_not_blank CHECK (length(trim(story_key)) > 0),
    CONSTRAINT user_stories_title_not_blank CHECK (length(trim(title)) > 0),
    CONSTRAINT user_stories_story_not_blank CHECK (length(trim(story_text)) > 0),
    CONSTRAINT user_stories_points_nonnegative CHECK (story_points IS NULL OR story_points >= 0),
    CONSTRAINT user_stories_current_version_positive CHECK (current_version > 0),
    CONSTRAINT user_stories_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0)),
    CONSTRAINT user_stories_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT user_stories_unique_key_per_project UNIQUE (project_id, story_key)
);

DO $$
BEGIN
    ALTER TABLE epics ADD COLUMN IF NOT EXISTS current_version INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE epics ADD COLUMN IF NOT EXISTS feedback TEXT;
    ALTER TABLE epics ADD COLUMN IF NOT EXISTS approval_feedback TEXT;
    ALTER TABLE epics ADD COLUMN IF NOT EXISTS approval_comments TEXT;

    ALTER TABLE features ADD COLUMN IF NOT EXISTS current_version INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE features ADD COLUMN IF NOT EXISTS feedback TEXT;
    ALTER TABLE features ADD COLUMN IF NOT EXISTS approval_feedback TEXT;
    ALTER TABLE features ADD COLUMN IF NOT EXISTS approval_comments TEXT;

    ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS feedback TEXT;
    ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS approval_feedback TEXT;
    ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS approval_comments TEXT;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'epics_current_version_positive') THEN
        ALTER TABLE epics ADD CONSTRAINT epics_current_version_positive CHECK (current_version > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'epics_regeneration_feedback_required') THEN
        ALTER TABLE epics ADD CONSTRAINT epics_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'features_current_version_positive') THEN
        ALTER TABLE features ADD CONSTRAINT features_current_version_positive CHECK (current_version > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'features_regeneration_feedback_required') THEN
        ALTER TABLE features ADD CONSTRAINT features_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_stories_regeneration_feedback_required') THEN
        ALTER TABLE user_stories ADD CONSTRAINT user_stories_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dependencies_user_story_fk') THEN
        ALTER TABLE dependencies
            ADD CONSTRAINT dependencies_user_story_fk FOREIGN KEY (user_story_id) REFERENCES user_stories(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS one_line_user_stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    epic_id UUID REFERENCES epics(id) ON DELETE SET NULL,
    feature_id UUID REFERENCES features(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES requirements(id) ON DELETE SET NULL,
    detailed_user_story_id UUID REFERENCES user_stories(id) ON DELETE SET NULL,
    story_key VARCHAR(80) NOT NULL,
    one_line_text TEXT NOT NULL,
    priority VARCHAR(40) NOT NULL DEFAULT 'medium',
    sort_order INTEGER NOT NULL DEFAULT 0,
    current_version INTEGER NOT NULL DEFAULT 1,
    feedback TEXT,
    approval_feedback TEXT,
    approval_comments TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT one_line_user_stories_key_not_blank CHECK (length(trim(story_key)) > 0),
    CONSTRAINT one_line_user_stories_text_not_blank CHECK (length(trim(one_line_text)) > 0),
    CONSTRAINT one_line_user_stories_current_version_positive CHECK (current_version > 0),
    CONSTRAINT one_line_user_stories_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0)),
    CONSTRAINT one_line_user_stories_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT one_line_user_stories_unique_key_per_project UNIQUE (project_id, story_key)
);

DO $$
BEGIN
    ALTER TABLE one_line_user_stories ADD COLUMN IF NOT EXISTS feedback TEXT;
    ALTER TABLE one_line_user_stories ADD COLUMN IF NOT EXISTS approval_feedback TEXT;
    ALTER TABLE one_line_user_stories ADD COLUMN IF NOT EXISTS approval_comments TEXT;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'one_line_user_stories_regeneration_feedback_required') THEN
        ALTER TABLE one_line_user_stories ADD CONSTRAINT one_line_user_stories_regeneration_feedback_required CHECK (current_version = 1 OR (feedback IS NOT NULL AND length(trim(feedback)) > 0));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS acceptance_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_story_id UUID NOT NULL REFERENCES user_stories(id) ON DELETE CASCADE,
    criterion_key VARCHAR(80) NOT NULL,
    criterion_text TEXT NOT NULL,
    given_clause TEXT,
    when_clause TEXT,
    then_clause TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    confidence_score NUMERIC(5,4),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT acceptance_criteria_key_not_blank CHECK (length(trim(criterion_key)) > 0),
    CONSTRAINT acceptance_criteria_text_not_blank CHECK (length(trim(criterion_text)) > 0),
    CONSTRAINT acceptance_criteria_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT acceptance_criteria_unique_key_per_story UNIQUE (user_story_id, criterion_key)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    job_id UUID NOT NULL,
    status validation_status NOT NULL,
    confidence_score NUMERIC(5,4) NOT NULL,
    threshold NUMERIC(5,4) NOT NULL,
    attempt_count SMALLINT NOT NULL DEFAULT 1,
    validator_model VARCHAR(160),
    validation_summary TEXT,
    validation_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT validation_confidence_range CHECK (confidence_score >= 0 AND confidence_score <= 1),
    CONSTRAINT validation_threshold_range CHECK (threshold >= 0 AND threshold <= 1),
    CONSTRAINT validation_attempt_range CHECK (attempt_count BETWEEN 1 AND 10),
    CONSTRAINT validation_latest_per_job UNIQUE (job_id)
);

CREATE TABLE IF NOT EXISTS approval_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    validation_result_id UUID REFERENCES validation_results(id) ON DELETE SET NULL,
    decision approval_decision NOT NULL DEFAULT 'pending',
    approved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    auto_approved BOOLEAN NOT NULL DEFAULT FALSE,
    confidence_score NUMERIC(5,4),
    notes TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT approval_confidence_range CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT approval_auto_consistency CHECK (
        (auto_approved = TRUE AND decision = 'auto_approved' AND approved_by_user_id IS NULL)
        OR
        (auto_approved = FALSE)
    ),
    CONSTRAINT approval_manual_consistency CHECK (
        decision <> 'manually_approved' OR approved_by_user_id IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS artifact_version_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    artifact_type VARCHAR(40) NOT NULL,
    artifact_id UUID NOT NULL,
    version_number INTEGER NOT NULL,
    feedback_type VARCHAR(40) NOT NULL,
    feedback TEXT NOT NULL,
    comments TEXT,
    provided_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    approval_status_id UUID REFERENCES approval_status(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT artifact_version_feedback_artifact_type_valid CHECK (artifact_type IN ('epic', 'feature', 'user_story', 'one_line_user_story')),
    CONSTRAINT artifact_version_feedback_type_valid CHECK (feedback_type IN ('regeneration', 'approval')),
    CONSTRAINT artifact_version_feedback_version_positive CHECK (version_number > 0),
    CONSTRAINT artifact_version_feedback_not_blank CHECK (length(trim(feedback)) > 0),
    CONSTRAINT artifact_version_feedback_regeneration_no_approval CHECK (
        feedback_type <> 'regeneration' OR approval_status_id IS NULL
    ),
    CONSTRAINT artifact_version_feedback_approval_has_approval CHECK (
        feedback_type <> 'approval' OR approval_status_id IS NOT NULL
    ),
    CONSTRAINT artifact_version_feedback_one_record_per_version_event UNIQUE (
        artifact_type,
        artifact_id,
        version_number,
        feedback_type
    )
);

CREATE TABLE IF NOT EXISTS exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    requested_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    export_format export_format NOT NULL,
    storage_uri TEXT NOT NULL,
    file_size_bytes BIGINT,
    checksum_sha256 CHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT exports_file_size_positive CHECK (file_size_bytes IS NULL OR file_size_bytes > 0),
    CONSTRAINT exports_checksum_hex CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS ai_generation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    job_id UUID NOT NULL,
    status generation_status NOT NULL,
    model_name VARCHAR(160),
    prompt_hash CHAR(64),
    response_hash CHAR(64),
    attempt_count SMALLINT NOT NULL DEFAULT 1,
    max_attempts SMALLINT NOT NULL DEFAULT 3,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    error_code VARCHAR(120),
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT ai_logs_attempt_range CHECK (attempt_count BETWEEN 1 AND 10),
    CONSTRAINT ai_logs_max_attempts_range CHECK (max_attempts BETWEEN 1 AND 10),
    CONSTRAINT ai_logs_tokens_nonnegative CHECK (
        (input_tokens IS NULL OR input_tokens >= 0)
        AND (output_tokens IS NULL OR output_tokens >= 0)
    ),
    CONSTRAINT ai_logs_duration_nonnegative CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT ai_logs_prompt_hash_hex CHECK (prompt_hash IS NULL OR prompt_hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT ai_logs_response_hash_hex CHECK (response_hash IS NULL OR response_hash ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    entity_type VARCHAR(120) NOT NULL,
    entity_id UUID,
    action VARCHAR(120) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT audit_entity_type_not_blank CHECK (length(trim(entity_type)) > 0),
    CONSTRAINT audit_action_not_blank CHECK (length(trim(action)) > 0)
);

COMMIT;
