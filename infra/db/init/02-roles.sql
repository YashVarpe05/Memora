-- Two roles, on purpose.
--
--   memora      owner + migrations. Superuser in this dev image.
--   memora_app  what the API connects as at runtime.
--
-- Superusers bypass RLS unconditionally, and FORCE ROW LEVEL SECURITY does not
-- change that. An API connected as the owner-superuser makes every policy inert
-- while every test still passes. memora_app owns nothing and cannot bypass.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'memora_app') THEN
    CREATE ROLE memora_app
      LOGIN PASSWORD 'memora_app'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE memora TO memora_app;
GRANT USAGE ON SCHEMA public TO memora_app;

-- Tables do not exist yet. Default privileges cover whatever migrations create,
-- so a new table is reachable by the app without a follow-up GRANT --- but is
-- still subject to its RLS policy.
ALTER DEFAULT PRIVILEGES FOR ROLE memora IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO memora_app;
ALTER DEFAULT PRIVILEGES FOR ROLE memora IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO memora_app;

-- Cover anything already present.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO memora_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO memora_app;
