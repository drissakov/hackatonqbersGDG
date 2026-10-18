"""Apply checked SQL once, atomically; no imports/embeddings or startup writes."""

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg import sql  # noqa: E402

from backend.app.database import DatabasePool, DatabaseUnavailable, schema_name  # noqa: E402
from backend.app.settings import Settings  # noqa: E402


def migrate(pool: DatabasePool, schema="app") -> bool:
    schema_name(schema)
    applied = False
    with pool.connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (schema,))
        connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        ledger = sql.Identifier(schema, "schema_migrations")
        connection.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {} (version text PRIMARY KEY, checksum text NOT NULL, "
                "applied_at timestamptz NOT NULL DEFAULT now())"
            ).format(ledger)
        )
        connection.execute("SELECT set_config('qadam.schema', %s, true)", (schema,))
        for path in sorted((ROOT / "database" / "migrations").glob("*.sql")):
            content = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode()).hexdigest()
            version = path.name.split("_", 1)[0]
            row = connection.execute(
                sql.SQL("SELECT checksum FROM {} WHERE version=%s").format(ledger), (version,)
            ).fetchone()
            if row:
                if row["checksum"] != checksum:
                    raise DatabaseUnavailable("migration_checksum_mismatch")
                continue
            connection.execute(content, prepare=False)
            connection.execute(
                sql.SQL("INSERT INTO {} (version,checksum) VALUES (%s,%s)").format(ledger),
                (version, checksum),
            )
            applied = True
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="app")
    parser.add_argument("--test-database", action="store_true")
    args = parser.parse_args()
    pool = None
    try:
        target = schema_name(args.schema)
        if args.test_database and target == "app":
            raise ValueError("Test migrations require an isolated test schema")
        url = (
            os.environ.get("TEST_DATABASE_URL", "")
            if args.test_database
            else Settings().database_url.get_secret_value()
        )
        pool = DatabasePool(url, max_size=1)
        applied = migrate(pool, target)
    except (DatabaseUnavailable, ValueError):
        print(
            "Migration failed: connection, permissions or schema/checksum configuration; "
            "values hidden"
        )
        return 1
    finally:
        if pool:
            pool.close()
    print(
        "Applied pending migrations"
        if applied
        else "Migrations already applied; checksums verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
