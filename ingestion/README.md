# D02: repeatable Astana OSM import

Run from the repository root with Python 3.12+ and the existing dependencies in
`backend/requirements.txt`. Development checks additionally use the existing
`backend/requirements-dev.txt`. No ingestion dependency was added.

```powershell
python -m ingestion.cli import-osm --city astana --export-only
python -m ingestion.cli import-osm --city astana
python -m ingestion.cli import-osm --city astana --from-snapshot data/raw/<import-id>.json --export-only
```

The second command exports before calling S01 `PostgresPOIRepository.upsert_pois`.
It reads the existing backend Settings configuration and closes its bounded
pool of at most two connections, respecting a smaller DATABASE_POOL_SIZE setting.
Upserts use batches of at most 100 records with at most two batches
in flight. S01 is atomic per batch; the entire city import is not one transaction.
Committed counts and unknown outcomes for failed batches are recorded separately.
Safe progress lines contain only indexes, counters and rejection codes.
If a process is interrupted after a batch commits, its final report may be absent;
rerun the same snapshot to reconcile stable identities without deleting POIs.
`--env-file PATH` selects another existing server env file;
process environment wins. Never paste connection strings into CLI arguments.
Missing configuration is `not_run`, an initialization failure is `failed`, and
failed individual batches make persistence `partial` with unknown batch outcomes.
This importer contains no SQL, migrations, delete or deactivate operation.
The S01 contract owns stable identity, transactional writes and stale rejection.

`--from-snapshot` only accepts an already available, permitted OSM raw snapshot
in `qadam-osm-snapshot-v1` format. It validates declared ODbL rights, provenance,
all category outcomes, timestamps, unique identities, exact query identity sets
and polygon geometry. It is not a converter for arbitrary dumps or 2GIS exports.
Do not relabel unlicensed data as OSM. Synthetic test inputs exist only in tests
and temporary test directories, never in the production corpus.

Default HTTP timeout: 60 seconds; Overpass execution timeout: five seconds less.
At most two retries and one concurrent category query by default. Options allow
10–120 seconds, 0–3 retries and concurrency 1–2. Retries respect bounded
Retry-After; requests asking for a longer pause fail safely rather than retrying
early. HTTP 403 is terminal; 429, transient failures, malformed JSON and missing
count sentinels never become successful empty results. The endpoint is explicit
in each snapshot, with no silent mirror fallback.

## Flow and outputs

`osm.py` discovers Astana's current admin-level-4 relation using official OSM
identity tags (KZ-71, historical KZ-AST or Wikidata Q1520). It joins relation
outer/inner ways, rejecting incomplete rings, and keeps MultiPolygon geometry.
Each allowlisted category gets a separate node/way/relation bbox query. Final
out-count sentinels and each unique query identity set detect incomplete output.
`normalize.py` clips representative coordinates against the boundary, preserves
OSM type/ID, normalizes text to NFC and validates every canonical POIRecord.

The finite category registry is `categories.py`. No earlier D00 registry was
present in the available merged source; this explicit D02 registry follows the
shared ActivityCode enum. The generated `data/source-registry.json` records the
allowlist, rights basis, source URL, fetch/base times and boundary identity.

- `data/normalized/pois.jsonl`: strict contract 1.1.0 canonical records.
- `data/normalized/manifest.json`: SHA-256, boundary geometry, source timestamps,
  category outcomes, coverage, language names, aliases and per-record facts.
- `data/normalized/first-10.jsonl`: first ten validated real records for review.
- `data/normalized/upsert-summary.json`: actual persistence status and counters;
  the local import ID is not an S01 database audit ID.
- `data/normalized/runs/<import-id>/`: immutable JSONL/manifest generation.
- `data/raw/<import-id>.json`: permitted raw snapshot, replayable without network.
- `data/reports/<import-id>.json` and `data/source-report.json`: import outcome.

Raw data, normalized exports, `data/reports/` run histories and transfer archives
are ignored by Git using `data/.gitignore`. Registry and compact source/quality
reports at the data root are intended
for review. Git does not deliver the corpus: transfer JSONL and manifest together.
All OSM exports retain attribution and the ODbL license URL. ODbL attribution and
share-alike obligations apply to distribution of derived data; see the source
rights basis at https://www.openstreetmap.org/copyright and the linked license.

## Consumer requirements and honest uncertainty

The manifest is mandatory. Contract 1.1.0 forbids additional canonical fields, so
language names, aliases, source-version times, coordinate accuracy and derived
markers live at `normalization.records[poi.id]`. S03 must join this sidecar before
using those facts. A way/relation center is an approximate representative point,
possibly outside its feature or the city; rejected centers are counted. The
canonical DB location alone cannot convey this uncertainty. No contract extension
or SQL change is made by D02; see the handoff request to Sabyrzhan.

Only `name:<language>` asserts an explicitly tagged language. `int_name` and
`alt_name` are aliases with no inferred language. Distinct OSM type/IDs, including
same-brand branches at the same coordinates, remain distinct. Exact repeated
identities choose the newest valid source version deterministically. Possible
cross-ID representations need later manual review, never automatic name merging.

The description labels a deterministic summary of actual OSM tags as derived.
Unknown hours, price, quietness, sockets and accessibility stay null. Direct
opening_hours text and wheelchair tags are retained as unverified source facts,
not a claim of opening or full accessibility. OSM edit/base times are source
timestamps, never fact observation or verification dates; verified_at stays null.
The snapshot fetched_at/canonical retrieved_at is a shared acquisition-session
timestamp set after boundary discovery, before category requests. It is not the
exact response time for each POI. Individual provider base timestamps and the
import report's start/finish window remain available; this is not a synchronized
point-in-time database dump.

`complete=true` means all seven allowed-category requests completed, not complete
city coverage. The real denominator is unknown. Coverage reports show counts,
rejections and a 4×4 bbox occupancy grid, whose cells can extend outside the city.
Detailed review of 10–30 venues belongs to D05/D06.

A partial category failure can export/upsert the valid subset, returns exit 2
and preserves prior database rows. Full outage or zero valid rows returns exit 1
and does not replace the previous normalized pair. Exit 0 means complete fetch
and successful requested mode (export-only explicitly skips the database).

One OS-level lock serializes imports per data directory. A second process fails
with `import_already_running`; process death releases the kernel lock. Each file
is replaced atomically and the manifest is published last. Consumers must verify
the JSONL SHA-256 before using the pair. A crash between the two replacements can
leave a mismatch: recover using the immutable generation identified by import ID.

## Verification

```powershell
python -m compileall -q backend/app scripts ingestion
python -m pytest backend/tests ingestion/tests -q
python -m ruff check backend scripts ingestion
python -m ruff format --check backend scripts ingestion
python scripts/export_contracts.py --check
```

The explicit ingestion test path is necessary because shared pytest discovery
currently lists only `backend/tests`. Schema-format validation and the shared
Pydantic model are both checked. Database integration tests require a disposable
TEST_DATABASE_URL; they never fall back to the production URL. See D02 handoff
for actual live commands, checks, hashes, transfer status and blockers.
