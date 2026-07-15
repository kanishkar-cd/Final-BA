-- Full schema bootstrap for new environments.
-- For production, prefer running migrations in order from database/migrations.

\ir ../migrations/001_init_extensions_and_types.sql
\ir ../migrations/002_create_tables.sql
\ir ../migrations/003_indexes_and_triggers.sql
\ir ../migrations/004_traceability_matrix.sql
\ir ../migrations/005_rag_bm25_fts.sql