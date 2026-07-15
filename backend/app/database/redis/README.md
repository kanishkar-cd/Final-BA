# Redis Cache Layer

Redis uses a hybrid cache model. Deterministic document preprocessing is shared
globally by document hash. Workflow, AI generation, validation, review, and
temporary output state is isolated by `user_id`.

Final approved BRD outputs are written to PostgreSQL. Redis stores current
planning and story read caches plus story version snapshots for rollback, but
PostgreSQL remains the source of truth for the latest approved rows.

## Global Cache

Global keys are safe to reuse across users because they are deterministic for
the same uploaded document bytes or normalized document hash.

| Key | Purpose | Default TTL |
| --- | --- | --- |
| `global:document:{document_hash}` | Document hash mapping and parser result summary | 30 days |
| `global:parsed:{document_hash}` | Parsed text or OCR output | 30 days |
| `global:chunks:{document_hash}` | Chunked text | 30 days |
| `global:embeddings:{document_hash}` | Embeddings derived only from deterministic chunks | 30 days |
| `global:metadata:{document_hash}` | Document metadata extracted during preprocessing | 30 days |

When another user uploads the exact same document hash, reuse these values
instead of parsing, OCRing, chunking, or embedding the document again.

## User-Scoped Cache

User keys isolate all state that can vary by user, project, prompt, approval
decision, business context, or iteration.

| Key | Purpose | Default TTL |
| --- | --- | --- |
| `user:{user_id}:session` | User session cache | 12 hours |
| `user:{user_id}:project:{project_id}:workflow` | Active workflow and current processing stage | 6 hours |
| `user:{user_id}:project:{project_id}:generation` | Current AI generation state and temporary draft | 6 hours |
| `user:{user_id}:project:{project_id}:generation:job:{job_id}:attempts` | Regeneration attempt list | 6 hours |
| `user:{user_id}:project:{project_id}:generation:job:{job_id}:latest_output` | Latest generated BRD/epics/stories draft before approval | 6 hours |
| `user:{user_id}:project:{project_id}:generation:job:{job_id}:validation` | Latest validation result | 6 hours |
| `user:{user_id}:project:{project_id}:iteration` | Current iteration and iteration history | 6 hours |
| `user:{user_id}:project:{project_id}:confidence` | Confidence score and scoring detail | 6 hours |
| `user:{user_id}:project:{project_id}:review` | BA review state, comments, and regeneration decision | 24 hours |
| `user:{user_id}:project:{project_id}:planning:actors:current` | Current approved actors for fast planning/story context reads | 24 hours |
| `user:{user_id}:project:{project_id}:planning:functional_requirements:current` | Current approved functional requirements | 24 hours |
| `user:{user_id}:project:{project_id}:planning:non_functional_requirements:current` | Current approved non-functional requirements | 24 hours |
| `user:{user_id}:project:{project_id}:planning:business_rules:current` | Current approved business rules | 24 hours |
| `user:{user_id}:project:{project_id}:planning:business_goals:current` | Current approved business goals | 24 hours |
| `user:{user_id}:project:{project_id}:planning:edge_cases:current` | Current approved edge cases | 24 hours |
| `user:{user_id}:project:{project_id}:planning:constraints:current` | Current approved constraints | 24 hours |
| `user:{user_id}:project:{project_id}:planning:dependencies:current` | Current approved dependencies | 24 hours |
| `user:{user_id}:project:{project_id}:planning:epics:current` | Current approved epics | 24 hours |
| `user:{user_id}:project:{project_id}:planning:features:current` | Current approved features | 24 hours |
| `user:{user_id}:project:{project_id}:planning:one_line_stories:current` | Current approved one-line planning stories | 24 hours |
| `user:{user_id}:project:{project_id}:stories:one_line:current` | Current one-line user stories for fast BA listing | 24 hours |
| `user:{user_id}:project:{project_id}:stories:one_line:{story_id}:versions` | One-line user story version snapshots for rollback, including BA regeneration feedback and approval comments | No default expiry |
| `user:{user_id}:project:{project_id}:stories:detailed:current` | Current detailed user stories for fast retrieval | 24 hours |
| `user:{user_id}:project:{project_id}:stories:detailed:{story_id}:versions` | Detailed user story version snapshots for rollback, including BA regeneration feedback and approval comments | No default expiry |
| `user:{user_id}:project:{project_id}:stories:version_keys` | Registry of per-story version keys for invalidation | No default expiry |
| `user:{user_id}:job:{job_id}:status` | Processing status for upload/generation flow | 6 hours |

Never globally cache BRDs, actors, requirements, business goals, edge cases,
constraints, business rules, dependencies, epics, user stories, acceptance
criteria, test cases, confidence scores, iteration history, BA comments,
review status, approved versions, draft versions, or workflow state. Planning
and story caches must stay under user-scoped
`user:{user_id}:project:{project_id}:planning:*` and
`user:{user_id}:project:{project_id}:stories:*` keys.

## Key Generators

Global generators live in `cache_keys.py`:

- `global_document(document_hash)`
- `global_parsed(document_hash)`
- `global_chunks(document_hash)`
- `global_embeddings(document_hash)`
- `global_metadata(document_hash)`

User generators live in the same module:

- `user_session(user_id)`
- `user_workflow(user_id, project_id)`
- `user_generation(user_id, project_id)`
- `user_iteration(user_id, project_id)`
- `user_confidence(user_id, project_id)`
- `user_review(user_id, project_id)`
- `user_actors_current(user_id, project_id)`
- `user_functional_requirements_current(user_id, project_id)`
- `user_non_functional_requirements_current(user_id, project_id)`
- `user_business_rules_current(user_id, project_id)`
- `user_business_goals_current(user_id, project_id)`
- `user_edge_cases_current(user_id, project_id)`
- `user_constraints_current(user_id, project_id)`
- `user_dependencies_current(user_id, project_id)`
- `user_epics_current(user_id, project_id)`
- `user_features_current(user_id, project_id)`
- `user_one_line_story_artifacts_current(user_id, project_id)`
- `user_one_line_stories_current(user_id, project_id)`
- `user_one_line_story_versions(user_id, project_id, story_id)`
- `user_detailed_stories_current(user_id, project_id)`
- `user_detailed_story_versions(user_id, project_id, story_id)`
- `user_story_version_registry(user_id, project_id)`
- `user_job(user_id, job_id)`

Planning and story helper functions live in `cache.py`:

- `cache_planning_artifacts(...)`
- `cache_actors(...)`
- `cache_functional_requirements(...)`
- `cache_non_functional_requirements(...)`
- `cache_business_rules(...)`
- `cache_business_goals(...)`
- `cache_edge_cases(...)`
- `cache_constraints(...)`
- `cache_dependencies(...)`
- `cache_epics(...)`
- `cache_features(...)`
- `cache_one_line_story_artifacts(...)`
- `cache_one_line_user_stories(...)`
- `append_one_line_user_story_version(...)`
- `cache_detailed_user_stories(...)`
- `append_detailed_user_story_version(...)`
- `invalidate_user_story_version_history(...)`

## Invalidation

- Parser, OCR, chunking, or embedding changes: call
  `invalidate_document_cache(redis, document_hash)` for affected document
  hashes.
- Approved artifacts committed to PostgreSQL: refresh the current planning and
  story caches, then call
  `invalidate_generation_cache(redis, user_id, project_id, job_id)`.
- Manual approval, rejection, BA comment changes, or export creation: call
  `invalidate_project_cache(redis, user_id, project_id)`.
- Story rollback: append the prior latest row to the appropriate version list,
  update PostgreSQL with the selected snapshot as the new latest row, then
  refresh `stories:one_line:current` or `stories:detailed:current`.
- Project or document purge: call
  `invalidate_user_story_version_history(redis, user_id, project_id)` if the
  rollback history should be removed with the owning records.
- Logout or session revocation: call `invalidate_user_session(redis, user_id)`.

## Usage

```python
from database.redis.redis_client import create_redis_client
from database.redis.cache import GenerationAttempt, append_generation_attempt, set_job_status

redis = create_redis_client()

await set_job_status(redis, user_id, job_id, "processing", {"document_hash": document_hash})
await append_generation_attempt(
    redis,
    user_id,
    project_id,
    job_id,
    GenerationAttempt(
        attempt_number=1,
        output={"epics": [], "features": [], "user_stories": []},
        confidence_score=0.82,
    ),
)
```

## Benefits

- Preprocessing work is reused safely for duplicate uploads.
- User workflow data cannot leak through shared Redis keys.
- Generation and review state has short TTLs and clear invalidation paths.
- Key naming makes ownership and sharing boundaries visible during operations.
