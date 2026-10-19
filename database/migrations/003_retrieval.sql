-- S03 preserves the canonical wire document and legacy source-hash invalidation.
DO $migration$
DECLARE
    target text := coalesce(nullif(current_setting('qadam.schema', true), ''), 'app');
    trgm text;
    role_name text;
BEGIN
    IF target <> 'app' AND target !~ '^test_s01_[a-f0-9]{12}$' THEN
        RAISE EXCEPTION 'Invalid migration schema';
    END IF;
    SELECT n.nspname INTO STRICT trgm FROM pg_extension e
        JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pg_trgm';
    EXECUTE format($ddl$
        CREATE TABLE %1$I.poi_search_documents (
            poi_id text PRIMARY KEY REFERENCES %1$I.pois(id) ON DELETE CASCADE,
            source_document jsonb NOT NULL,
            indexed_text text NOT NULL,
            text_hash text NOT NULL CHECK (text_hash ~ '^[a-f0-9]{64}$'),
            text_version text NOT NULL,
            names text NOT NULL,
            metadata jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX poi_search_names_idx ON %1$I.poi_search_documents
            USING gin (names %2$I.gin_trgm_ops);
        ALTER TABLE %1$I.embeddings ADD COLUMN text_version text NOT NULL DEFAULT 'legacy-s01';
        ALTER TABLE %1$I.embeddings ADD COLUMN document_text_hash text;
        ALTER TABLE %1$I.embeddings ADD CONSTRAINT embedding_document_hash
            CHECK (document_text_hash IS NULL OR document_text_hash ~ '^[a-f0-9]{64}$');
        CREATE TRIGGER search_document_rights BEFORE INSERT OR UPDATE
            ON %1$I.poi_search_documents FOR EACH ROW
            EXECUTE FUNCTION %1$I.check_embedding_rights();
        CREATE FUNCTION %1$I.invalidate_search_document() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
        BEGIN
            IF NEW.document IS DISTINCT FROM OLD.document OR NOT NEW.indexing_allowed THEN
                DELETE FROM %1$I.poi_search_documents WHERE poi_id=NEW.id;
            END IF;
            RETURN NEW;
        END
        $body$;
        CREATE TRIGGER pois_search_invalidation AFTER UPDATE OF document,indexing_allowed
            ON %1$I.pois FOR EACH ROW EXECUTE FUNCTION %1$I.invalidate_search_document();
        ALTER TABLE %1$I.poi_search_documents ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON %1$I.poi_search_documents FROM PUBLIC;
    $ddl$, target, trgm);
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON %I.poi_search_documents FROM %I', target, role_name);
        END IF;
    END LOOP;
END
$migration$;
