DO
$$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aura_service') THEN
        CREATE ROLE aura_service LOGIN PASSWORD 'aura_service' BYPASSRLS;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aura_app') THEN
        CREATE ROLE aura_app LOGIN PASSWORD 'aura_app' NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE aura TO aura_service;
GRANT CONNECT ON DATABASE aura TO aura_app;
