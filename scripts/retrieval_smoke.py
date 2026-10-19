"""Read-only S03 probes against the real corpus; never log user inputs or credentials."""

import argparse
import asyncio
import json
from pathlib import Path

from backend.app.database import DatabasePool, DatabaseUnavailable
from backend.app.indexing import DIMENSIONS, EMBEDDING_MODEL, TEXT_VERSION
from backend.app.openai_client import OpenAIClient
from backend.app.repository import PostgresPOIRepository
from backend.app.retrieval import Retriever
from backend.app.schemas import RecommendationRequest
from backend.app.settings import Settings
from scripts.embed_pois import ROOT, load_corpus


async def probe(repository, client, corpus, lexical_only):
    records, _, evidence = corpus
    museums = [p for p in records.values() if p.activity_code == "museum" and len(p.name) < 1800]
    if not museums:
        return {"status": "not_run", "reason": "no_museum_probe_record"}
    named = museums[0]
    cases = [
        (
            "kk",
            RecommendationRequest(
                query="Мұражайға барғым келеді, 60 минутым бар, бюджетім 2000 теңгеге дейін, "
                "ғимарат ішінде, бастапқы жерге қайтуым керек.",
                locale="en",
            ),
        ),
        (
            "ru",
            RecommendationRequest(
                query="Хочу посмотреть музей в помещении. Есть 45 минут, до 1500 тенге, "
                "нужно вернуться.",
                locale="kk",
            ),
        ),
        (
            "en",
            RecommendationRequest(
                query="Find a museum indoors, at most 90 minutes, budget up to 3000 KZT. "
                "I need to return to the start.",
                locale="ru",
            ),
        ),
        (
            "mixed_name",
            RecommendationRequest(query=f"{named.name} museum мұражай музей", locale="en"),
        ),
        (
            "explicit_conflict",
            RecommendationRequest(
                query="I need at least 60 minutes for a museum.",
                available_minutes=20,
                explicit_fields=["available_minutes"],
            ),
        ),
    ]
    if lexical_only:
        cases = [("lexical_real_name", RecommendationRequest(query=named.name, locale="kk"))]
    results = []
    retriever = Retriever(repository, client)
    for case_id, request in cases:
        result = await retriever.retrieve(request, limit=3)
        resolved = result.intent.intent
        results.append(
            {
                "case": case_id,
                "status": result.status,
                "intent_status": result.intent.status,
                "intent_reason": result.intent.reason,
                "clarification_fields": result.intent.clarification_fields,
                "resolved": resolved.model_dump(mode="json", exclude={"query", "origin"})
                if resolved
                else None,
                "diagnostics": result.diagnostics,
                "candidates": [
                    candidate.model_dump(mode="json") for candidate in result.candidates
                ],
            }
        )
    if lexical_only:
        passed = results[0]["status"] == "ok" and results[0]["diagnostics"]["mode"] == "lexical"
    else:
        passed = (
            all(
                r["status"] == "ok"
                and r["intent_status"] == "ok"
                and r["diagnostics"]["mode"] == "hybrid"
                for r in results[:-1]
            )
            and results[-1]["status"] == "clarification"
        )
        expected = {"kk": (60, 2000), "ru": (45, 1500), "en": (90, 3000)}
        for row in results[:3]:
            resolved = row["resolved"] or {}
            minutes, budget = expected[row["case"]]
            passed = passed and (
                resolved.get("available_minutes") == minutes
                and resolved.get("budget_kzt_per_person") == budget
                and resolved.get("indoor") == "indoor"
                and resolved.get("return_to_start") is True
                and "museum" in resolved.get("categories", [])
            )
        passed = (
            passed
            and bool(results[3]["candidates"])
            and (results[3]["candidates"][0]["id"] == named.id)
        )
    unavailable = any(
        r["intent_status"] == "unavailable" or r["status"] == "unavailable" for r in results
    )
    return {
        "status": "passed" if passed else "not_run" if unavailable else "failed",
        "corpus": evidence,
        "embedding_space": {
            "model": EMBEDDING_MODEL,
            "dimensions": DIMENSIONS,
            "text_version": TEXT_VERSION,
        },
        "probes": results,
    }


async def run(args):
    corpus = load_corpus(
        ROOT / "data/normalized/pois.jsonl", ROOT / "data/normalized/manifest.json"
    )
    settings = Settings()
    pool = DatabasePool(settings.database_url.get_secret_value(), max_size=1)
    try:
        repository = PostgresPOIRepository(pool)
        if args.lexical_only or not settings.openai_api_key.get_secret_value():
            return await probe(repository, None, corpus, args.lexical_only)
        async with OpenAIClient(settings) as client:
            return await probe(repository, client, corpus, False)
    finally:
        pool.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args))
    except DatabaseUnavailable:
        report = {"status": "unavailable", "reason": "database_unavailable"}
    except (OSError, ValueError, TypeError, KeyError):
        report = {"status": "not_run", "reason": "corpus_or_configuration_invalid"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", "utf-8")
    # Full public source candidates are in the local report for the S04 consumer.
    print(
        json.dumps(
            {
                "status": report["status"],
                "probes": [
                    {
                        "case": p["case"],
                        "status": p["status"],
                        "intent_status": p["intent_status"],
                        "candidate_ids": [c["id"] for c in p["candidates"]],
                    }
                    for p in report.get("probes", [])
                ],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
