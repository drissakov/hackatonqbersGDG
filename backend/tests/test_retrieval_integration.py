"""Actual PostGIS/pg_trgm/pgvector execution, only in disposable TEST_DATABASE_URL."""

import asyncio

from psycopg import sql

from backend.app.indexing import build_document
from backend.app.schemas import Coordinates, POIRecord
from backend.tests.test_repository_integration import record, upsert
from backend.tests.test_repository_integration import repository as repository_fixture

repository = repository_fixture

VECTOR = [1.0] + [0.0] * 1535


def run(operation):
    return asyncio.run(operation)


def search(repo, query, **kwargs):
    return run(repo.retrieve_candidates(query, **kwargs))


def control(repo):
    row = record("retrieval-control")
    row.update(name="Unique control needle", activity_code="museum")
    upsert(repo, [row])
    poi = POIRecord.model_validate(row)
    details = {
        "source_id": poi.primary_source_id,
        "names": {"kk": "Әлем көрмесі", "ru": "Галерея Мира", "en": "World Gallery"},
        "aliases": ["Әлем Gallery"],
        "facts": {},
    }
    document = build_document(poi, details)
    assert run(repo.save_search_document(document, VECTOR)) == "saved"
    return row, document


def test_multilingual_aliases_nfc_fuzzy_names_categories_and_geo(repository):
    repo = repository
    row, _ = control(repo)
    for term in ("Әлем көрмесі", "Галерея Мира", "World Gallery", "Әлем Gallery", "Worlt Gallery"):
        found = search(repo, term)
        assert found[0]["id"] == row["id"] and found[0]["lexical_score"] >= 0.35
    assert search(repo, "irrelevant zzxx", categories=["museum"])[0]["category_match"]
    assert (
        search(
            repo, "Әлем Gallery", origin=Coordinates(latitude=51.128, longitude=71.43), radius_m=100
        )[0]["distance_m"]
        < 100
    )
    assert (
        search(repo, "Әлем Gallery", origin=Coordinates(latitude=0, longitude=0), radius_m=100)
        == []
    )


def test_vector_space_metadata_and_dimensions_actually_gate_sql_similarity(repository):
    repo = repository
    row, _ = control(repo)
    found = search(repo, "zzxxqq unrelated", vector=VECTOR)
    assert found[0]["semantic_score"] == 1.0
    with repo.pool.connection() as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET model='different-model' WHERE poi_id=%s").format(
                repo.table("embeddings")
            ),
            (row["id"],),
        )
    assert search(repo, "zzxxqq unrelated", vector=VECTOR) == []
    # Mismatching embeddings must not remove valid lexical matches.
    found = search(repo, "Әлем Gallery", vector=VECTOR)
    assert found[0]["semantic_score"] is None


def test_control_update_and_delete_change_retrieval_and_invalidate_old_aliases(repository):
    repo = repository
    row, document = control(repo)
    assert search(repo, "Әлем Gallery")
    row["name"] = "Completely different needle"
    upsert(repo, [row])
    assert search(repo, "Әлем Gallery") == []
    assert search(repo, "Completely different needle")[0]["document"]["name"] == row["name"]
    assert run(repo.save_search_document(document, VECTOR)) == "stale"
    with repo.pool.connection() as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE id=%s").format(repo.table("pois")), (row["id"],)
        )
    assert search(repo, "Completely different needle") == []


def test_rights_revocation_removes_search_index_and_excludes_poi(repository):
    repo = repository
    row, _ = control(repo)
    row["sources"][0]["indexing_allowed"] = False
    upsert(repo, [row])
    assert search(repo, "Unique control needle", categories=["museum"], vector=VECTOR) == []
    with repo.pool.connection() as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(repo.table("poi_search_documents"))
            ).fetchone()["n"]
            == 0
        )


def test_unchanged_upsert_keeps_index_and_production_repository_excludes_synthetic(repository):
    from backend.app.repository import PostgresPOIRepository

    row, _ = control(repository)
    upsert(repository, [row])
    assert search(repository, "Әлем Gallery")
    production = PostgresPOIRepository(repository.pool, schema=repository.schema)
    assert search(production, "Әлем Gallery", vector=VECTOR) == []


def test_other_text_version_falls_back_to_current_canonical_name(repository):
    row, _ = control(repository)
    with repository.pool.connection() as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET text_version='different-version'").format(
                repository.table("poi_search_documents")
            )
        )
    found = search(repository, row["name"], vector=VECTOR)
    assert found and found[0]["semantic_score"] is None
    assert search(repository, "Әлем Gallery") == []
