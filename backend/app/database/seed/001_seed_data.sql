-- Minimal seed data for local development and smoke testing.
-- Replace storage_uri values with your object storage paths in real environments.

BEGIN;

INSERT INTO users (id, email, full_name, role)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin@example.com', 'System Administrator', 'admin'),
    ('00000000-0000-0000-0000-000000000002', 'ba@example.com', 'Business Analyst', 'business_analyst')
ON CONFLICT (email) DO NOTHING;

INSERT INTO projects (
    id,
    owner_user_id,
    name,
    description,
    confidence_threshold,
    max_regeneration_attempts
)
VALUES (
    '10000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    'Sample BA Accelerator Project',
    'Seed project showing approved latest-only storage.',
    0.8500,
    3
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO documents (
    id,
    project_id,
    uploaded_by_user_id,
    original_filename,
    storage_uri,
    mime_type,
    file_size_bytes,
    checksum_sha256,
    status,
    parsed_text_hash,
    parser_name,
    parser_version
)
VALUES (
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    'sample-brd.pdf',
    's3://example-bucket/sample-brd.pdf',
    'application/pdf',
    524288,
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'approved',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'docling',
    '1.0.0'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO document_chunks (
    id,
    document_id,
    project_id,
    chunk_index,
    section_title,
    content,
    token_count,
    content_hash
)
VALUES (
    '21000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    0,
    'Customer Registration',
    'The system shall allow customers to register using email and mobile number.',
    14,
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
)
ON CONFLICT (document_id, chunk_index) DO NOTHING;

INSERT INTO requirements (
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    requirement_type,
    priority,
    confidence_score
)
VALUES (
    '30000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    'REQ-001',
    'Customer registration',
    'Customers can register with email and mobile number.',
    'functional',
    'high',
    0.9200
)
ON CONFLICT (document_id, requirement_code) DO NOTHING;

INSERT INTO requirements (
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_code,
    title,
    description,
    requirement_type,
    priority,
    confidence_score
)
VALUES (
    '30000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    'NFR-001',
    'Registration performance',
    'Registration submission should complete within two seconds under normal load.',
    'non_functional',
    'medium',
    0.8700
)
ON CONFLICT (document_id, requirement_code) DO NOTHING;

INSERT INTO actors (
    id,
    project_id,
    document_id,
    source_chunk_id,
    actor_name,
    actor_type,
    description,
    confidence_score
)
VALUES (
    '31000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    'Customer',
    'external',
    'Person registering for access to the service.',
    0.9100
)
ON CONFLICT (document_id, actor_name) DO NOTHING;

INSERT INTO business_goals (
    id,
    project_id,
    document_id,
    source_chunk_id,
    goal_code,
    title,
    description,
    confidence_score
)
VALUES (
    '34000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    'BG-001',
    'Improve customer onboarding',
    'Increase successful customer onboarding through a simple registration flow.',
    0.8800
)
ON CONFLICT (document_id, goal_code) DO NOTHING;

INSERT INTO edge_cases (
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_id,
    edge_case_code,
    title,
    description,
    expected_behavior,
    confidence_score
)
VALUES (
    '35000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    'EC-001',
    'Duplicate registration attempt',
    'A customer attempts to register with contact details that already exist.',
    'The system rejects the registration and explains that the account already exists.',
    0.8400
)
ON CONFLICT (document_id, edge_case_code) DO NOTHING;

INSERT INTO constraints (
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_id,
    constraint_code,
    title,
    description,
    constraint_type,
    confidence_score
)
VALUES (
    '36000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    'CON-001',
    'Verified contact required',
    'Registration must capture a reachable email address and mobile number.',
    'business',
    0.8300
)
ON CONFLICT (document_id, constraint_code) DO NOTHING;

INSERT INTO business_rules (
    id,
    project_id,
    document_id,
    source_chunk_id,
    requirement_id,
    rule_code,
    title,
    description,
    rule_type,
    confidence_score
)
VALUES (
    '32000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    'BR-001',
    'Unique customer contact details',
    'A customer email address and mobile number must not already belong to an active account.',
    'eligibility',
    0.8600
)
ON CONFLICT (document_id, rule_code) DO NOTHING;

INSERT INTO dependencies (
    id,
    project_id,
    document_id,
    source_chunk_id,
    source_requirement_id,
    dependency_code,
    dependency_name,
    description,
    dependency_type,
    status,
    confidence_score
)
VALUES (
    '33000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    'DEP-001',
    'Customer identity service',
    'Registration depends on the customer identity service being available for account creation.',
    'internal_service',
    'identified',
    0.8500
)
ON CONFLICT (document_id, dependency_code) DO NOTHING;

INSERT INTO epics (
    id,
    project_id,
    document_id,
    epic_key,
    title,
    description,
    priority,
    one_line_story,
    business_value,
    sort_order,
    confidence_score
)
VALUES (
    '40000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'EPIC-001',
    'Account onboarding',
    'Capabilities needed to onboard new customers.',
    'high',
    'Customers can create an account using verified contact details.',
    'Improves customer acquisition and activation.',
    1,
    0.9100
)
ON CONFLICT (project_id, epic_key) DO NOTHING;

INSERT INTO features (
    id,
    project_id,
    document_id,
    epic_id,
    feature_key,
    title,
    description,
    priority,
    sort_order,
    confidence_score
)
VALUES (
    '50000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '40000000-0000-0000-0000-000000000001',
    'FEAT-001',
    'Registration form',
    'Capture customer identity fields required for registration.',
    'high',
    1,
    0.9000
)
ON CONFLICT (project_id, feature_key) DO NOTHING;

INSERT INTO user_stories (
    id,
    project_id,
    document_id,
    feature_id,
    epic_id,
    requirement_id,
    story_key,
    title,
    user_role,
    goal,
    benefit,
    story_text,
    priority,
    story_points,
    sort_order,
    confidence_score
)
VALUES (
    '60000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '50000000-0000-0000-0000-000000000001',
    '40000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    'US-001',
    'Register with contact details',
    'customer',
    'register using email and mobile number',
    'I can create an account and access the service',
    'As a customer, I want to register using email and mobile number so that I can create an account and access the service.',
    'high',
    3,
    1,
    0.8900
)
ON CONFLICT (project_id, story_key) DO NOTHING;

INSERT INTO one_line_user_stories (
    id,
    project_id,
    document_id,
    feature_id,
    requirement_id,
    detailed_user_story_id,
    story_key,
    one_line_text,
    priority,
    sort_order,
    confidence_score
)
VALUES (
    '61000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '50000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    '60000000-0000-0000-0000-000000000001',
    'US-001',
    'Customer can register using email and mobile number.',
    'high',
    1,
    0.8900
)
ON CONFLICT (project_id, story_key) DO NOTHING;

INSERT INTO acceptance_criteria (
    id,
    project_id,
    document_id,
    user_story_id,
    criterion_key,
    criterion_text,
    given_clause,
    when_clause,
    then_clause,
    sort_order,
    confidence_score
)
VALUES (
    '70000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '60000000-0000-0000-0000-000000000001',
    'AC-001',
    'Given a new customer, when valid email and mobile number are submitted, then the system creates a pending customer account.',
    'a new customer provides valid registration details',
    'the customer submits the registration form',
    'the system creates a pending customer account',
    1,
    0.8800
)
ON CONFLICT (user_story_id, criterion_key) DO NOTHING;

INSERT INTO validation_results (
    id,
    project_id,
    document_id,
    job_id,
    status,
    confidence_score,
    threshold,
    attempt_count,
    validator_model,
    validation_summary
)
VALUES (
    '80000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '90000000-0000-0000-0000-000000000001',
    'passed',
    0.8900,
    0.8500,
    1,
    'validator-model',
    'Generated output passed confidence threshold.'
)
ON CONFLICT (job_id) DO NOTHING;

INSERT INTO approval_status (
    id,
    project_id,
    document_id,
    validation_result_id,
    decision,
    auto_approved,
    confidence_score,
    notes,
    decided_at
)
VALUES (
    '81000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '80000000-0000-0000-0000-000000000001',
    'auto_approved',
    TRUE,
    0.8900,
    'Auto-approved by confidence threshold.',
    now()
)
ON CONFLICT DO NOTHING;

COMMIT;
