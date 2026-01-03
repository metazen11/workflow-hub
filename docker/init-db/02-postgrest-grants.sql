-- PostgREST table grants for web_anon/web_user
-- Ensure CRUD access for API usage (adjust as needed for stricter policies)

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO web_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO web_anon;
GRANT DELETE ON TABLE public.work_cycles TO web_anon;
GRANT UPDATE ON TABLE public.tasks TO web_anon;

-- Allow future tables to inherit privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO web_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO web_anon;
