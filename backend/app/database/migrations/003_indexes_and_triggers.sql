-- Migration 003: update triggers and production indexes.

BEGIN;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'users',
        'projects',
        'documents',
        'document_chunks',
        'requirements',
        'actors',
        'functional_requirements',
        'non_functional_requirements',
        'business_rules',
        'dependencies',
        'business_goals',
        'edge_cases',
        'constraints',
        'epics',
        'features',
        'user_stories',
        'one_line_user_stories',
        'acceptance_criteria',
        'validation_results',
        'approval_status',
        'artifact_version_feedback',
        'exports',
        'ai_generation_logs'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', 'trg_' || table_name || '_updated_at', table_name);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            'trg_' || table_name || '_updated_at',
            table_name
        );
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_active_created_at ON users (is_active, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_email_trgm_ready ON users (email) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_projects_owner_status ON projects (owner_user_id, status, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_projects_status_created_at ON projects (status, created_at DESC) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_documents_project_status ON documents (project_id, status, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents (uploaded_by_user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_documents_checksum ON documents (checksum_sha256);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_order ON document_chunks (document_id, chunk_index) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_document_chunks_project ON document_chunks (project_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_hash ON document_chunks (content_hash);

CREATE INDEX IF NOT EXISTS idx_requirements_project_document ON requirements (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_requirements_document_code ON requirements (document_id, requirement_code) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_requirements_source_chunk ON requirements (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_requirements_title_search ON requirements USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_actors_project_document ON actors (project_id, document_id, actor_name) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_actors_source_chunk ON actors (source_chunk_id) WHERE source_chunk_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_functional_requirements_project_document ON functional_requirements (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_functional_requirements_requirement ON functional_requirements (requirement_id);
CREATE INDEX IF NOT EXISTS idx_functional_requirements_source_chunk ON functional_requirements (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_functional_requirements_search ON functional_requirements USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_non_functional_requirements_project_document ON non_functional_requirements (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_non_functional_requirements_requirement ON non_functional_requirements (requirement_id);
CREATE INDEX IF NOT EXISTS idx_non_functional_requirements_source_chunk ON non_functional_requirements (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_non_functional_requirements_quality_attribute ON non_functional_requirements (quality_attribute) WHERE quality_attribute IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_non_functional_requirements_search ON non_functional_requirements USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_business_rules_project_document ON business_rules (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_business_rules_requirement ON business_rules (requirement_id) WHERE requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_business_rules_source_chunk ON business_rules (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_business_rules_search ON business_rules USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_dependencies_project_document ON dependencies (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_source_requirement ON dependencies (source_requirement_id) WHERE source_requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_depends_on_requirement ON dependencies (depends_on_requirement_id) WHERE depends_on_requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_epic ON dependencies (epic_id) WHERE epic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_feature ON dependencies (feature_id) WHERE feature_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_user_story ON dependencies (user_story_id) WHERE user_story_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_source_chunk ON dependencies (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dependencies_search ON dependencies USING gin (to_tsvector('english', coalesce(dependency_name, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_business_goals_project_document ON business_goals (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_business_goals_source_chunk ON business_goals (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_business_goals_search ON business_goals USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_edge_cases_project_document ON edge_cases (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_edge_cases_requirement ON edge_cases (requirement_id) WHERE requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_edge_cases_source_chunk ON edge_cases (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_edge_cases_search ON edge_cases USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(expected_behavior, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_constraints_project_document ON constraints (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_constraints_requirement ON constraints (requirement_id) WHERE requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_constraints_source_chunk ON constraints (source_chunk_id) WHERE source_chunk_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_constraints_search ON constraints USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_epics_project_document ON epics (project_id, document_id, sort_order, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_epics_title_search ON epics USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_features_project_document ON features (project_id, document_id, sort_order, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_features_epic ON features (epic_id, sort_order) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_features_title_search ON features USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_stories_project_document ON user_stories (project_id, document_id, sort_order, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_stories_feature ON user_stories (feature_id, sort_order) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_stories_requirement ON user_stories (requirement_id) WHERE requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_stories_search ON user_stories USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(story_text, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_one_line_user_stories_project_document ON one_line_user_stories (project_id, document_id, sort_order, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_one_line_user_stories_epic ON one_line_user_stories (epic_id, sort_order) WHERE epic_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_one_line_user_stories_feature ON one_line_user_stories (feature_id, sort_order) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_one_line_user_stories_requirement ON one_line_user_stories (requirement_id) WHERE requirement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_one_line_user_stories_detailed ON one_line_user_stories (detailed_user_story_id) WHERE detailed_user_story_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_one_line_user_stories_search ON one_line_user_stories USING gin (to_tsvector('english', coalesce(one_line_text, ''))) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_acceptance_criteria_project_document ON acceptance_criteria (project_id, document_id, sort_order, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_acceptance_criteria_story ON acceptance_criteria (user_story_id, sort_order) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_validation_project_document ON validation_results (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_validation_status_created_at ON validation_results (status, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_validation_job ON validation_results (job_id);

CREATE INDEX IF NOT EXISTS idx_approval_project_document ON approval_status (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_approval_decision_created_at ON approval_status (decision, created_at DESC) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_approval_one_open_per_document
    ON approval_status (document_id)
    WHERE deleted_at IS NULL AND decision IN ('pending', 'needs_regeneration');

CREATE INDEX IF NOT EXISTS idx_artifact_version_feedback_project_document
    ON artifact_version_feedback (project_id, document_id, created_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_artifact_version_feedback_artifact
    ON artifact_version_feedback (artifact_type, artifact_id, version_number, feedback_type)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_artifact_version_feedback_approval
    ON artifact_version_feedback (approval_status_id)
    WHERE approval_status_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_exports_project_created_at ON exports (project_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_exports_document_created_at ON exports (document_id, created_at DESC) WHERE document_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ai_logs_project_document ON ai_generation_logs (project_id, document_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ai_logs_job_created_at ON ai_generation_logs (job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_logs_status_created_at ON ai_generation_logs (status, created_at DESC) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_audit_project_created_at ON audit_logs (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_document_created_at ON audit_logs (document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_created_at ON audit_logs (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs (entity_type, entity_id, created_at DESC);

COMMIT;
