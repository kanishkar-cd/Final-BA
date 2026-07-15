-- Migration 005: RAG layer – BM25 full-text search support on document_chunks.
--
-- Adds:
--   1. `content_tsv`  tsvector column on document_chunks (auto-maintained by trigger)
--   2. GIN index on content_tsv for sub-millisecond tsquery searches
--   3. `context_label` text column to expose the context label produced by the
--      context labeling service so BM25 queries can filter by business domain
--   4. `embedding_indexed_at` timestamptz to track when a chunk was last pushed
--      to Qdrant (NULL = not yet indexed)
--   5. Helper function rag_tsquery() to safely cast a plain-text query string to
--      tsquery, falling back to websearch_to_tsquery when plainto_tsquery is empty

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────────
-- 1.  New columns on document_chunks
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS content_tsv        tsvector,
    ADD COLUMN IF NOT EXISTS context_label      TEXT,
    ADD COLUMN IF NOT EXISTS embedding_indexed_at TIMESTAMPTZ;

-- Back-fill tsvector for any rows that already exist
UPDATE document_chunks
SET    content_tsv = to_tsvector('english',
           coalesce(section_title, '') || ' ' || coalesce(content, ''))
WHERE  content_tsv IS NULL
  AND  deleted_at  IS NULL;

-- ──────────────────────────────────────────────────────────────────────────────
-- 2.  Trigger to keep content_tsv up-to-date automatically
-- ──────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION document_chunks_tsv_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.content_tsv :=
        to_tsvector('english',
            coalesce(NEW.section_title, '') || ' ' || coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_chunks_tsv ON document_chunks;

CREATE TRIGGER trg_document_chunks_tsv
    BEFORE INSERT OR UPDATE OF section_title, content
    ON document_chunks
    FOR EACH ROW
    EXECUTE FUNCTION document_chunks_tsv_update();

-- ──────────────────────────────────────────────────────────────────────────────
-- 3.  GIN index for fast full-text search
-- ──────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_document_chunks_content_fts
    ON document_chunks USING gin (content_tsv)
    WHERE deleted_at IS NULL;

-- Supporting index for project-scoped BM25 queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_project_fts
    ON document_chunks (project_id, embedding_indexed_at)
    WHERE deleted_at IS NULL;

-- Supporting index for document-scoped BM25 queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_fts
    ON document_chunks (document_id, embedding_indexed_at)
    WHERE deleted_at IS NULL;

-- Index for finding chunks that still need Qdrant indexing
CREATE INDEX IF NOT EXISTS idx_document_chunks_unindexed
    ON document_chunks (project_id, document_id, chunk_index)
    WHERE deleted_at IS NULL
      AND embedding_indexed_at IS NULL;

-- ──────────────────────────────────────────────────────────────────────────────
-- 4.  Helper function: safe tsquery construction
--     Accepts a plain-text query string, tries plainto_tsquery first,
--     falls back to websearch_to_tsquery so that single-token requirement IDs
--     like "FR-001" are handled without error.
-- ──────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION rag_tsquery(query_text TEXT)
RETURNS tsquery AS $$
DECLARE
    result tsquery;
BEGIN
    -- Attempt strict phrase parsing first
    BEGIN
        result := plainto_tsquery('english', query_text);
        IF result IS NOT NULL THEN
            RETURN result;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        NULL; -- fall through
    END;

    -- Fall back to web-search style (handles hyphens, quotes, etc.)
    RETURN websearch_to_tsquery('english', query_text);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ──────────────────────────────────────────────────────────────────────────────
-- 5.  Helper view: chunk_search_view
--     Joins document_chunks with documents and projects so the BM25 service
--     can retrieve all metadata it needs in a single query.
-- ──────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW chunk_search_view AS
SELECT
    dc.id                    AS chunk_id,
    dc.document_id,
    dc.project_id,
    dc.chunk_index,
    dc.section_title,
    dc.context_label,
    dc.content,
    dc.token_count,
    dc.content_hash,
    dc.metadata               AS chunk_metadata,
    dc.embedding_indexed_at,
    dc.created_at             AS chunk_created_at,
    d.original_filename,
    d.mime_type,
    d.metadata                AS document_metadata
FROM   document_chunks dc
JOIN   documents        d  ON d.id = dc.document_id
WHERE  dc.deleted_at IS NULL
  AND  d.deleted_at  IS NULL;

COMMIT;
