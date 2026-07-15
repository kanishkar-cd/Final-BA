-- Migration 004: traceability links, issue tracking, and matrix views.
-- Purpose: trace any validation issue or generation problem back to the exact
-- source chunk, planning artifact, requirement, epic, feature, story, criterion,
-- validation result, or AI run that needs action.

BEGIN;

CREATE TABLE IF NOT EXISTS traceability_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    source_entity_type VARCHAR(80) NOT NULL,
    source_entity_id UUID NOT NULL,
    target_entity_type VARCHAR(80) NOT NULL,
    target_entity_id UUID NOT NULL,
    relationship_type VARCHAR(80) NOT NULL,
    confidence_score NUMERIC(5,4),
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    detection_source VARCHAR(120),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT trace_links_source_type_check CHECK (
        source_entity_type IN (
            'document',
            'document_chunk',
            'actor',
            'requirement',
            'functional_requirement',
            'non_functional_requirement',
            'business_rule',
            'dependency',
            'business_goal',
            'edge_case',
            'constraint',
            'epic',
            'feature',
            'user_story',
            'one_line_user_story',
            'acceptance_criteria',
            'validation_result',
            'approval_status',
            'export',
            'ai_generation_log',
            'audit_log',
            'traceability_issue'
        )
    ),
    CONSTRAINT trace_links_target_type_check CHECK (
        target_entity_type IN (
            'document',
            'document_chunk',
            'actor',
            'requirement',
            'functional_requirement',
            'non_functional_requirement',
            'business_rule',
            'dependency',
            'business_goal',
            'edge_case',
            'constraint',
            'epic',
            'feature',
            'user_story',
            'one_line_user_story',
            'acceptance_criteria',
            'validation_result',
            'approval_status',
            'export',
            'ai_generation_log',
            'audit_log',
            'traceability_issue'
        )
    ),
    CONSTRAINT trace_links_relationship_not_blank CHECK (length(trim(relationship_type)) > 0),
    CONSTRAINT trace_links_confidence_range CHECK (
        confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)
    ),
    CONSTRAINT trace_links_no_self_link CHECK (
        source_entity_type <> target_entity_type OR source_entity_id <> target_entity_id
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_traceability_links_active
    ON traceability_links (
        project_id,
        source_entity_type,
        source_entity_id,
        target_entity_type,
        target_entity_id,
        relationship_type
    )
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_links_project_document
    ON traceability_links (project_id, document_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_links_source
    ON traceability_links (source_entity_type, source_entity_id, relationship_type)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_links_target
    ON traceability_links (target_entity_type, target_entity_id, relationship_type)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_links_relationship
    ON traceability_links (relationship_type, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS traceability_issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    validation_result_id UUID REFERENCES validation_results(id) ON DELETE SET NULL,
    ai_generation_log_id UUID REFERENCES ai_generation_logs(id) ON DELETE SET NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id UUID NOT NULL,
    issue_type VARCHAR(120) NOT NULL,
    severity VARCHAR(40) NOT NULL DEFAULT 'medium',
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    issue_summary TEXT NOT NULL,
    issue_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommended_action TEXT,
    detected_by VARCHAR(120),
    detection_source VARCHAR(120),
    assigned_to_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT trace_issues_entity_type_check CHECK (
        entity_type IN (
            'document',
            'document_chunk',
            'actor',
            'requirement',
            'functional_requirement',
            'non_functional_requirement',
            'business_rule',
            'dependency',
            'business_goal',
            'edge_case',
            'constraint',
            'epic',
            'feature',
            'user_story',
            'one_line_user_story',
            'acceptance_criteria',
            'validation_result',
            'approval_status',
            'export',
            'ai_generation_log'
        )
    ),
    CONSTRAINT trace_issues_issue_type_not_blank CHECK (length(trim(issue_type)) > 0),
    CONSTRAINT trace_issues_summary_not_blank CHECK (length(trim(issue_summary)) > 0),
    CONSTRAINT trace_issues_severity_check CHECK (
        severity IN ('low', 'medium', 'high', 'critical')
    ),
    CONSTRAINT trace_issues_status_check CHECK (
        status IN ('open', 'in_progress', 'resolved', 'ignored')
    ),
    CONSTRAINT trace_issues_resolution_consistency CHECK (
        (status = 'resolved' AND resolved_at IS NOT NULL)
        OR
        (status <> 'resolved')
    )
);

CREATE INDEX IF NOT EXISTS idx_trace_issues_project_status
    ON traceability_issues (project_id, status, severity, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_issues_document_status
    ON traceability_issues (document_id, status, created_at DESC)
    WHERE document_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_issues_entity
    ON traceability_issues (entity_type, entity_id, status, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_issues_validation
    ON traceability_issues (validation_result_id, created_at DESC)
    WHERE validation_result_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_trace_issues_ai_log
    ON traceability_issues (ai_generation_log_id, created_at DESC)
    WHERE ai_generation_log_id IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_traceability_links_updated_at ON traceability_links;
CREATE TRIGGER trg_traceability_links_updated_at
    BEFORE UPDATE ON traceability_links
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_traceability_issues_updated_at ON traceability_issues;
CREATE TRIGGER trg_traceability_issues_updated_at
    BEFORE UPDATE ON traceability_issues
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE VIEW traceability_matrix AS
SELECT
    r.project_id,
    r.document_id,
    d.original_filename,
    dc.id AS source_chunk_id,
    dc.chunk_index AS source_chunk_index,
    dc.section_title AS source_section_title,
    r.id AS requirement_id,
    r.requirement_code,
    r.title AS requirement_title,
    r.requirement_type,
    r.priority AS requirement_priority,
    r.confidence_score AS requirement_confidence_score,
    fr.id AS functional_requirement_id,
    nfr.id AS non_functional_requirement_id,
    e.id AS epic_id,
    e.epic_key,
    e.title AS epic_title,
    f.id AS feature_id,
    f.feature_key,
    f.title AS feature_title,
    ols.id AS one_line_user_story_id,
    ols.story_key AS one_line_story_key,
    ols.one_line_text,
    us.id AS user_story_id,
    us.story_key,
    us.title AS user_story_title,
    ac.id AS acceptance_criteria_id,
    ac.criterion_key,
    ac.criterion_text,
    (
        SELECT count(*)
        FROM traceability_issues ti
        WHERE ti.project_id = r.project_id
          AND ti.deleted_at IS NULL
          AND ti.status IN ('open', 'in_progress')
          AND (
              (ti.entity_type = 'document_chunk' AND ti.entity_id = dc.id)
              OR (ti.entity_type = 'requirement' AND ti.entity_id = r.id)
              OR (ti.entity_type = 'functional_requirement' AND ti.entity_id = fr.id)
              OR (ti.entity_type = 'non_functional_requirement' AND ti.entity_id = nfr.id)
              OR (ti.entity_type = 'epic' AND ti.entity_id = e.id)
              OR (ti.entity_type = 'feature' AND ti.entity_id = f.id)
              OR (ti.entity_type = 'one_line_user_story' AND ti.entity_id = ols.id)
              OR (ti.entity_type = 'user_story' AND ti.entity_id = us.id)
              OR (ti.entity_type = 'acceptance_criteria' AND ti.entity_id = ac.id)
          )
    ) AS open_issue_count
FROM requirements r
JOIN documents d
    ON d.id = r.document_id
LEFT JOIN document_chunks dc
    ON dc.id = r.source_chunk_id
    AND dc.deleted_at IS NULL
LEFT JOIN functional_requirements fr
    ON fr.requirement_id = r.id
    AND fr.deleted_at IS NULL
LEFT JOIN non_functional_requirements nfr
    ON nfr.requirement_id = r.id
    AND nfr.deleted_at IS NULL
LEFT JOIN user_stories us
    ON us.requirement_id = r.id
    AND us.deleted_at IS NULL
LEFT JOIN features f
    ON f.id = us.feature_id
    AND f.deleted_at IS NULL
LEFT JOIN epics e
    ON e.id = f.epic_id
    AND e.deleted_at IS NULL
LEFT JOIN one_line_user_stories ols
    ON (
        ols.detailed_user_story_id = us.id
        OR (ols.requirement_id = r.id AND ols.feature_id = f.id)
    )
    AND ols.deleted_at IS NULL
LEFT JOIN acceptance_criteria ac
    ON ac.user_story_id = us.id
    AND ac.deleted_at IS NULL
WHERE r.deleted_at IS NULL
  AND d.deleted_at IS NULL;

CREATE OR REPLACE VIEW traceability_issue_summary AS
SELECT
    ti.id AS issue_id,
    ti.project_id,
    ti.document_id,
    ti.validation_result_id,
    ti.ai_generation_log_id,
    ti.entity_type,
    ti.entity_id,
    CASE ti.entity_type
        WHEN 'document' THEN d.original_filename
        WHEN 'document_chunk' THEN coalesce(dc.section_title, 'Chunk ' || dc.chunk_index::text)
        WHEN 'actor' THEN actor.actor_name
        WHEN 'requirement' THEN req.requirement_code || ': ' || req.title
        WHEN 'functional_requirement' THEN fr.requirement_code || ': ' || fr.title
        WHEN 'non_functional_requirement' THEN nfr.requirement_code || ': ' || nfr.title
        WHEN 'business_rule' THEN br.rule_code || ': ' || br.title
        WHEN 'dependency' THEN dep.dependency_name
        WHEN 'business_goal' THEN bg.goal_code || ': ' || bg.title
        WHEN 'edge_case' THEN ec.edge_case_code || ': ' || ec.title
        WHEN 'constraint' THEN con.constraint_code || ': ' || con.title
        WHEN 'epic' THEN epic.epic_key || ': ' || epic.title
        WHEN 'feature' THEN feature.feature_key || ': ' || feature.title
        WHEN 'user_story' THEN story.story_key || ': ' || story.title
        WHEN 'one_line_user_story' THEN one_line.story_key || ': ' || one_line.one_line_text
        WHEN 'acceptance_criteria' THEN ac.criterion_key
        WHEN 'validation_result' THEN vr.status::text || ' validation result'
        WHEN 'approval_status' THEN approval.decision::text || ' approval status'
        WHEN 'export' THEN exp.export_format::text || ' export'
        WHEN 'ai_generation_log' THEN ai_log.status::text || ' AI generation log'
        ELSE ti.entity_type
    END AS entity_label,
    ti.issue_type,
    ti.severity,
    ti.status,
    ti.issue_summary,
    ti.recommended_action,
    ti.detected_by,
    ti.detection_source,
    ti.assigned_to_user_id,
    ti.resolved_by_user_id,
    ti.created_at,
    ti.updated_at,
    ti.resolved_at
FROM traceability_issues ti
LEFT JOIN documents d
    ON ti.entity_type = 'document'
    AND ti.entity_id = d.id
LEFT JOIN document_chunks dc
    ON ti.entity_type = 'document_chunk'
    AND ti.entity_id = dc.id
LEFT JOIN actors actor
    ON ti.entity_type = 'actor'
    AND ti.entity_id = actor.id
LEFT JOIN requirements req
    ON ti.entity_type = 'requirement'
    AND ti.entity_id = req.id
LEFT JOIN functional_requirements fr
    ON ti.entity_type = 'functional_requirement'
    AND ti.entity_id = fr.id
LEFT JOIN non_functional_requirements nfr
    ON ti.entity_type = 'non_functional_requirement'
    AND ti.entity_id = nfr.id
LEFT JOIN business_rules br
    ON ti.entity_type = 'business_rule'
    AND ti.entity_id = br.id
LEFT JOIN dependencies dep
    ON ti.entity_type = 'dependency'
    AND ti.entity_id = dep.id
LEFT JOIN business_goals bg
    ON ti.entity_type = 'business_goal'
    AND ti.entity_id = bg.id
LEFT JOIN edge_cases ec
    ON ti.entity_type = 'edge_case'
    AND ti.entity_id = ec.id
LEFT JOIN constraints con
    ON ti.entity_type = 'constraint'
    AND ti.entity_id = con.id
LEFT JOIN epics epic
    ON ti.entity_type = 'epic'
    AND ti.entity_id = epic.id
LEFT JOIN features feature
    ON ti.entity_type = 'feature'
    AND ti.entity_id = feature.id
LEFT JOIN user_stories story
    ON ti.entity_type = 'user_story'
    AND ti.entity_id = story.id
LEFT JOIN one_line_user_stories one_line
    ON ti.entity_type = 'one_line_user_story'
    AND ti.entity_id = one_line.id
LEFT JOIN acceptance_criteria ac
    ON ti.entity_type = 'acceptance_criteria'
    AND ti.entity_id = ac.id
LEFT JOIN validation_results vr
    ON ti.entity_type = 'validation_result'
    AND ti.entity_id = vr.id
LEFT JOIN approval_status approval
    ON ti.entity_type = 'approval_status'
    AND ti.entity_id = approval.id
LEFT JOIN exports exp
    ON ti.entity_type = 'export'
    AND ti.entity_id = exp.id
LEFT JOIN ai_generation_logs ai_log
    ON ti.entity_type = 'ai_generation_log'
    AND ti.entity_id = ai_log.id
WHERE ti.deleted_at IS NULL;

COMMIT;
