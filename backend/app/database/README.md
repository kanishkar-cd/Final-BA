# Business Analyst Accelerator Database Layer

This folder contains only the database layer for the AI-powered Business Analyst Accelerator:

- PostgreSQL schema and migrations
- production indexes and constraints
- seed data
- Redis cache key strategy and helper functions

It intentionally does not include frontend, backend APIs, AI agents, or a vector database.

## Folder Structure

```text
database/
|-- migrations/
|-- schema/
|-- indexes/
|-- seed/
|-- redis/
`-- README.md
```

## Data Flow

1. User uploads a BRD or requirement document.
2. The application computes a deterministic `document_hash`.
3. Parsed text, OCR output, metadata, chunks, and embeddings may be reused from
   Redis under `global:*` keys when another user uploads the same document hash.
4. Actors, requirements, business goals, edge cases, constraints, business rules, dependencies, epics, features, detailed stories, one-line stories, and acceptance criteria are generated.
5. Temporary generation attempts are stored in Redis under
   `user:{user_id}:project:{project_id}:generation:*`.
6. Current one-line/detailed story lists and their rollback history are stored
   in user-scoped Redis story keys.
7. AI validation writes the latest temporary validation result to a user-scoped
   Redis key.
8. If confidence passes the project threshold, the output can be auto-approved.
9. If confidence is low, regenerate up to the configured limit, default `3`.
10. Only the latest approved output is committed to PostgreSQL.
11. After commit, temporary user-scoped generation keys are invalidated.

## PostgreSQL Setup

Create the database:

```bash
createdb ba_accelerator
```

Apply migrations in order:

```bash
psql -d ba_accelerator -f database/migrations/001_init_extensions_and_types.sql
psql -d ba_accelerator -f database/migrations/002_create_tables.sql
psql -d ba_accelerator -f database/migrations/003_indexes_and_triggers.sql
psql -d ba_accelerator -f database/migrations/004_traceability_matrix.sql
```

For a fresh local environment, you can apply the full schema:

```bash
psql -d ba_accelerator -f database/schema/full_schema.sql
```

Load seed data:

```bash
psql -d ba_accelerator -f database/seed/001_seed_data.sql
```

## Core Relationships

- `users` own `projects`.
- `projects` contain uploaded `documents`.
- `documents` contain `document_chunks`.
- `requirements` reference source documents and optionally source chunks.
- `functional_requirements` and `non_functional_requirements` classify requirement rows while preserving `requirements` as the shared compatibility anchor.
- `actors`, `business_goals`, `edge_cases`, `constraints`, `business_rules`, and `dependencies` store extracted planning context linked to projects, documents, chunks, and requirements where applicable.
- `epics` belong to projects/documents.
- `features` belong to epics.
- `user_stories` store the latest detailed story per key, belong to features, and may link back to requirements.
- `one_line_user_stories` store the latest concise story per key for quick BA review and may link to detailed stories.
- `acceptance_criteria` belong to user stories.
- `validation_results` store the latest persisted validation outcome per `job_id`.
- `approval_status` supports pending, auto-approved, manually approved, rejected, and regeneration decisions.
- `exports`, `ai_generation_logs`, and `audit_logs` provide operational traceability.
- `traceability_links` stores explicit relationships between source chunks, planning artifacts, requirements, epics, features, one-line stories, detailed stories, acceptance criteria, validation runs, AI logs, and issues.
- `traceability_issues` stores exact problems against the affected artifact and the action required.
- `traceability_matrix` is a read-only coverage view from source chunk to requirement, epic, feature, story, and acceptance criteria with open issue counts.
- `traceability_issue_summary` is a read-only issue view that labels each issue with the exact affected artifact.

## Traceability Matrix

Traceability is implemented as relationship storage plus issue tracking:

1. `traceability_links` answers "how is this item connected?"
2. `traceability_issues` answers "what is wrong, where is it, and what action is required?"
3. `traceability_matrix` gives the frontend/backend a matrix view: `source chunk -> requirement -> epic -> feature -> one-line story -> detailed story -> acceptance criteria -> open issue count`.
4. `traceability_issue_summary` gives issue rows with an `entity_label`, so an error can point directly to the affected actor, requirement, epic, feature, story, criterion, dependency, source chunk, validation result, or AI run.

When generation or validation runs, the backend should create links such as:

- `document_chunk -> requirement` with relationship `derived_from`
- `requirement -> functional_requirement` or `requirement -> non_functional_requirement` with relationship `classified_as`
- `requirement -> epic` with relationship `covered_by`
- `epic -> feature` with relationship `decomposes_to`
- `feature -> one_line_user_story` with relationship `summarized_by`
- `one_line_user_story -> user_story` with relationship `expanded_to`
- `user_story -> acceptance_criteria` with relationship `validated_by`
- `validation_result -> feature` or `validation_result -> user_story` with relationship `reported_issue_on`

When a problem is detected, write one `traceability_issues` row against the exact affected entity. For example, if Feature F-003 is missing acceptance criteria, store:

- `entity_type = 'feature'`
- `entity_id = <feature uuid>`
- `issue_type = 'missing_acceptance_criteria'`
- `severity = 'high'`
- `status = 'open'`
- `recommended_action = 'Generate acceptance criteria for linked user stories.'`

The frontend can then show the issue on the exact feature and trace backward to its epic, requirement, and source document chunk.

## Latest-Only Storage Rule

PostgreSQL should not store every regeneration version. The application should use a transaction when approval is reached:

1. Delete or soft-delete prior approved artifacts for the document if replacing output.
2. Insert the latest approved actors, requirements, classified requirements, business goals, edge cases, constraints, business rules, dependencies, epics, features, detailed stories, one-line stories, criteria, validation result, and approval status.
3. Insert an `ai_generation_logs` row with hashes, token counts, status, and attempt count only.
4. Insert `traceability_links` for approved artifact relationships.
5. Insert `traceability_issues` for unresolved validation or coverage problems that must remain visible after commit.
6. Do not write rejected draft payloads, historical attempts, or prior story versions to PostgreSQL.
7. Delete Redis keys for
   `user:{user_id}:project:{project_id}:generation:job:{job_id}:attempts`,
   `user:{user_id}:project:{project_id}:generation:job:{job_id}:latest_output`,
   `user:{user_id}:project:{project_id}:generation:job:{job_id}:validation`,
   and `user:{user_id}:job:{job_id}:status`.

## User Story Versioning

PostgreSQL stores only the current approved version:

- `user_stories.current_version` identifies the current detailed story version.
- `one_line_user_stories.current_version` identifies the current one-line story version.
- Prior detailed and one-line story versions are stored in Redis under user-scoped story keys.
- Rollback should read the target Redis version snapshot, write it as the latest PostgreSQL row, increment `current_version`, and refresh the current Redis story cache.

## Redis Setup

Install the lightweight helper dependency if you want to use the included Python Redis utilities:

```bash
pip install -r database/redis/requirements.txt
```

Set connection environment variables:

```bash
export REDIS_URL=redis://localhost:6379/0
export REDIS_SOCKET_TIMEOUT_SECONDS=5
export REDIS_CONNECT_TIMEOUT_SECONDS=5
```

On Windows PowerShell:

```powershell
$env:REDIS_URL = "redis://localhost:6379/0"
```

Redis keys:

- `global:document:{document_hash}`
- `global:parsed:{document_hash}`
- `global:chunks:{document_hash}`
- `global:embeddings:{document_hash}`
- `global:metadata:{document_hash}`
- `user:{user_id}:session`
- `user:{user_id}:project:{project_id}:workflow`
- `user:{user_id}:project:{project_id}:generation`
- `user:{user_id}:project:{project_id}:iteration`
- `user:{user_id}:project:{project_id}:confidence`
- `user:{user_id}:project:{project_id}:review`
- `user:{user_id}:project:{project_id}:planning:actors:current`
- `user:{user_id}:project:{project_id}:planning:functional_requirements:current`
- `user:{user_id}:project:{project_id}:planning:non_functional_requirements:current`
- `user:{user_id}:project:{project_id}:planning:business_rules:current`
- `user:{user_id}:project:{project_id}:planning:business_goals:current`
- `user:{user_id}:project:{project_id}:planning:edge_cases:current`
- `user:{user_id}:project:{project_id}:planning:constraints:current`
- `user:{user_id}:project:{project_id}:planning:dependencies:current`
- `user:{user_id}:project:{project_id}:planning:epics:current`
- `user:{user_id}:project:{project_id}:planning:features:current`
- `user:{user_id}:project:{project_id}:planning:one_line_stories:current`
- `user:{user_id}:project:{project_id}:stories:one_line:current`
- `user:{user_id}:project:{project_id}:stories:one_line:{story_id}:versions`
- `user:{user_id}:project:{project_id}:stories:detailed:current`
- `user:{user_id}:project:{project_id}:stories:detailed:{story_id}:versions`
- `user:{user_id}:project:{project_id}:stories:version_keys`
- `user:{user_id}:job:{job_id}:status`

See [redis/README.md](redis/README.md) for helper functions, TTLs, and invalidation rules.

## Production Notes

- Use UUID primary keys generated by `pgcrypto`.
- `created_at`, `updated_at`, and `deleted_at` are present on mutable domain tables.
- `audit_logs` is append-only and uses `created_at`.
- Frequently filtered fields have indexes for `project_id`, `document_id`, `status`, `created_at`, ownership, and search text.
- Soft deletion is supported through `deleted_at`; foreign keys still preserve referential integrity.
- Use object storage for original files and exports; PostgreSQL stores the URI and checksum.
