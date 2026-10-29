-- Initial schema for DORA Platform development database
-- This runs on first container startup via docker-entrypoint-initdb.d

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create roles
-- Application role (non-superuser, read/write)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'dora_app') THEN
        CREATE ROLE dora_app WITH LOGIN PASSWORD 'change-me';
    END IF;
END
$$;

-- Grafana read-only role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'grafana_ro') THEN
        CREATE ROLE grafana_ro WITH LOGIN PASSWORD 'change-me';
    END IF;
END
$$;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO dora_app;
GRANT USAGE ON SCHEMA public TO grafana_ro;

-- Default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dora_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;

-- Note: Tables are created by Alembic migrations
-- This script only sets up roles and extensions
-- Run `make migrate` after container starts to create tables
