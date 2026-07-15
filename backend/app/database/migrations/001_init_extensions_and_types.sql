-- Business Analyst Accelerator database layer
-- Migration 001: PostgreSQL extensions and shared enum types.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_status') THEN
        CREATE TYPE project_status AS ENUM ('active', 'archived', 'deleted');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_status') THEN
        CREATE TYPE document_status AS ENUM (
            'uploaded',
            'parsing',
            'parsed',
            'processing',
            'approved',
            'rejected',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'approval_decision') THEN
        CREATE TYPE approval_decision AS ENUM (
            'pending',
            'auto_approved',
            'manually_approved',
            'rejected',
            'needs_regeneration'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'validation_status') THEN
        CREATE TYPE validation_status AS ENUM ('passed', 'failed', 'needs_review');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'generation_status') THEN
        CREATE TYPE generation_status AS ENUM ('started', 'regenerated', 'approved', 'rejected', 'failed');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'export_format') THEN
        CREATE TYPE export_format AS ENUM ('pdf', 'docx', 'xlsx', 'csv', 'json', 'jira');
    END IF;
END $$;

COMMIT;
