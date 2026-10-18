-- Apply atomically with scripts/migrate.py; never from the application startup.
-- Existing extension locations are preserved, including non-extensions schemas.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

DO $migration$
DECLARE
    target text := coalesce(nullif(current_setting('qadam.schema', true), ''), 'app');
    geo text;
    vec text;
    trgm text;
    role_name text;
BEGIN
    IF target <> 'app' AND target !~ '^test_s01_[a-f0-9]{12}$' THEN
        RAISE EXCEPTION 'Invalid migration schema';
    END IF;
    SELECT n.nspname INTO STRICT geo FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'postgis';
    SELECT n.nspname INTO STRICT vec FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector';
    SELECT n.nspname INTO STRICT trgm FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'pg_trgm';
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', target);
    -- Required for extension functions/operators used internally during DDL.
    PERFORM set_config('search_path', format('pg_catalog,%I,%I,%I,%I', target, geo, vec, trgm), true);
    EXECUTE format($ddl$
        CREATE TABLE %1$I.pois (
            id text PRIMARY KEY,
            source text NOT NULL CHECK (source IN ('osm','municipal','organizer','test_fixture','other')),
            source_item_id text NOT NULL,
            document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
            location %2$I.geography(Point,4326),
            indexed_text text NOT NULL,
            indexed_text_hash text NOT NULL CHECK (indexed_text_hash ~ '^[a-f0-9]{64}$'),
            indexing_allowed boolean NOT NULL,
            primary_observed_at timestamptz,
            is_test boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (source, source_item_id),
            UNIQUE (id, indexed_text_hash),
            CHECK (source <> 'test_fixture' OR is_test)
        );
        CREATE INDEX pois_location_idx ON %1$I.pois USING gist (location);
        CREATE INDEX pois_text_idx ON %1$I.pois USING gin (indexed_text %4$I.gin_trgm_ops);
        CREATE TABLE %1$I.poi_sources (
            poi_id text NOT NULL REFERENCES %1$I.pois(id) ON DELETE CASCADE,
            source_id text NOT NULL,
            provider text NOT NULL CHECK (provider <> 'twogis'),
            retrieved_at timestamptz NOT NULL,
            storage_allowed boolean NOT NULL CHECK (storage_allowed),
            indexing_allowed boolean NOT NULL,
            document jsonb NOT NULL,
            PRIMARY KEY (poi_id, source_id),
            CHECK (nullif(document->>'license', '') IS NOT NULL),
            CHECK (nullif(document->>'rights_basis_url', '') IS NOT NULL)
        );
        CREATE TABLE %1$I.poi_facts (
            poi_id text NOT NULL,
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            source_id text NOT NULL,
            source_item_id text NOT NULL,
            fields text[] NOT NULL CHECK (cardinality(fields) > 0),
            observed_at timestamptz,
            PRIMARY KEY (poi_id, ordinal),
            FOREIGN KEY (poi_id, source_id) REFERENCES %1$I.poi_sources(poi_id, source_id)
                ON DELETE CASCADE
        );
        CREATE TABLE %1$I.embeddings (
            poi_id text PRIMARY KEY,
            indexed_text_hash text NOT NULL,
            model text NOT NULL CHECK (length(btrim(model)) > 0),
            dimensions integer NOT NULL CHECK (dimensions = 1536),
            embedding %3$I.vector(1536) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (poi_id, indexed_text_hash)
                REFERENCES %1$I.pois(id, indexed_text_hash) ON DELETE CASCADE
        );
        CREATE TABLE %1$I.import_runs (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz NOT NULL DEFAULT now(),
            status text NOT NULL CHECK (status IN ('completed','failed')),
            attempted integer NOT NULL CHECK (attempted >= 0),
            inserted integer NOT NULL CHECK (inserted >= 0),
            updated integer NOT NULL CHECK (updated >= 0),
            rejected integer NOT NULL CHECK (rejected >= 0),
            error_code text CHECK (error_code IS NULL OR error_code = 'database_operation_failed'),
            CHECK (status = 'failed' OR attempted = inserted + updated + rejected)
        );
        CREATE FUNCTION %1$I.check_embedding_rights() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $body$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM %1$I.pois
                           WHERE id = NEW.poi_id AND indexing_allowed) THEN
                RAISE EXCEPTION 'Embedding requires indexing rights' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $body$;
        CREATE TRIGGER embeddings_rights BEFORE INSERT OR UPDATE ON %1$I.embeddings
            FOR EACH ROW EXECUTE FUNCTION %1$I.check_embedding_rights();
    $ddl$, target, geo, vec, trgm);
    -- Defense in depth: no Data API grants and no client-facing RLS policies.
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', target);
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I', target, role_name);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I', target, role_name);
        END IF;
    END LOOP;
    EXECUTE format('ALTER TABLE %I.pois ENABLE ROW LEVEL SECURITY', target);
    EXECUTE format('ALTER TABLE %I.poi_sources ENABLE ROW LEVEL SECURITY', target);
    EXECUTE format('ALTER TABLE %I.poi_facts ENABLE ROW LEVEL SECURITY', target);
    EXECUTE format('ALTER TABLE %I.embeddings ENABLE ROW LEVEL SECURITY', target);
    EXECUTE format('ALTER TABLE %I.import_runs ENABLE ROW LEVEL SECURITY', target);
END
$migration$;
