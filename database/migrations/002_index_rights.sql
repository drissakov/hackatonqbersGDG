-- Follow-up to already applied 001: storage permission alone is not indexing rights.
DO $migration$
DECLARE
    target text := coalesce(nullif(current_setting('qadam.schema', true), ''), 'app');
    trgm text;
BEGIN
    IF target <> 'app' AND target !~ '^test_s01_[a-f0-9]{12}$' THEN
        RAISE EXCEPTION 'Invalid migration schema';
    END IF;
    SELECT n.nspname INTO STRICT trgm FROM pg_extension e
        JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pg_trgm';
    EXECUTE format($ddl$
        DROP INDEX %1$I.pois_text_idx;
        DROP INDEX %1$I.pois_location_idx;
        CREATE INDEX pois_text_idx ON %1$I.pois
            USING gin (indexed_text %2$I.gin_trgm_ops) WHERE indexing_allowed;
        CREATE INDEX pois_location_idx ON %1$I.pois
            USING gist (location) WHERE indexing_allowed;
        CREATE OR REPLACE FUNCTION %1$I.check_embedding_rights() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
        BEGIN
            -- Serialize embedding writes against concurrent source-rights revocation.
            PERFORM 1 FROM %1$I.pois WHERE id=NEW.poi_id AND indexing_allowed FOR SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Embedding requires indexing rights' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END
        $body$;
    $ddl$, target, trgm);
END
$migration$;
