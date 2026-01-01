-- PostgREST Role Setup
-- Creates roles for anonymous and authenticated API access

-- Anonymous role (read-only public access)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'web_anon') THEN
        CREATE ROLE web_anon NOLOGIN;
    END IF;
END
$$;

-- Authenticated role (full CRUD access)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'web_user') THEN
        CREATE ROLE web_user NOLOGIN;
    END IF;
END
$$;

-- Authenticator role (PostgREST connects as this, then switches to anon/user)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticator') THEN
        CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgrest_password';
    END IF;
END
$$;

-- Grant role switching
GRANT web_anon TO authenticator;
GRANT web_user TO authenticator;

-- Grant schema access
GRANT USAGE ON SCHEMA public TO web_anon, web_user;

-- Grant table permissions (applied after migrations create tables)
-- These will be applied by a separate migration after tables exist
