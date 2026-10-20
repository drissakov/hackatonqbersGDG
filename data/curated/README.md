# Source-checked POI feature supplement

This small derivative dataset is distributed under the [Open Database License
1.0](https://opendatacommons.org/licenses/odbl/1-0/), with attribution to
**© OpenStreetMap contributors**. Storage and indexing permissions follow the
[OSM copyright and license statement](https://www.openstreetmap.org/copyright).
This does not grant reuse rights for any unrelated venue website or provider.

`poi-features.json` contains 22 real Astana playground records, separate from
the existing indexed city corpus. `source-audit.json` retains the source
projection, complete way geometry, source versions/edit dates, acquisition URLs,
SHA-256, boundary clipping evidence, exclusions and query failures.

## What was checked

The official OSM API was queried on 2026-10-20 for the reviewed source IDs and
all nodes needed to reconstruct their way geometry. This verifies the published
community records as retrieved. It is **not** an on-site inspection, an operator
confirmation or a guarantee that a venue is currently operating or safe.

- All 22 records explicitly have `leisure=playground`, whose documented meaning
  is an area designed for children to play.
- Eleven explicitly have `access=yes`. Public access for the other eleven is
  unknown; absence of the tag never becomes a positive permission claim.
- No age admission, staff supervision, safety, free admission, accessibility,
  quietness or customer power outlet is inferred from the playground tag.
- All source names are absent. `Unnamed playground (OSM way/...)` and the node
  equivalent are derived labels. Source provenance never claims these names.
- Area locations are interior representative points, marked approximate; they
  are not verified entrances. The one node keeps its source coordinates.
- Source edit timestamps are retained separately from retrieval/check time.
  Every `observed_at` remains null because no physical observation was made.

Three close alternatives were omitted from the explicit public-access subset.
Private, customer-only and childcare-institution candidates were not selected.
Two initial candidates outside the recorded Astana administrative boundary were
also excluded. The eleven additional playgrounds with unknown access are at
least 500 metres from other already selected records; they remain conditional.
The supplement is not an assertion of complete Astana coverage.

## Charging evidence gap

The source audit records a completed, zero-result OSM search covering the
registered Astana administrative bounding box for outlet/device-charging tags.
**Zero cafes have qualified branch-specific customer outlet evidence.** This
does not mean cafes lack outlets. Wi-Fi, a grid connection, EV charging, brand
claims or an electrical installation do not establish a customer phone socket.
No unlicensed operator content is stored, embedded or indexed here.

## Validate and refresh

From the repository root, with the existing backend environment installed:

```powershell
python -m ingestion.curated validate
python -m pytest ingestion/tests/test_curated.py -q
```

Validation is offline. It compares every catalog record and evidence item with
the deterministic source projection, validates the shared runtime and POI models,
checks source rights and SHA-256, and clips locations to the saved city boundary.
The test command additionally validates all POIs against their generated JSON
Schema. Neither command connects to a database or embedding provider.

To refresh the same reviewed OSM IDs intentionally:

```powershell
python -m ingestion.curated refresh
python -m ingestion.curated validate
```

The refresh command uses the official public OSM API with bounded response sizes
and timeouts. It refreshes source versions, geometry and explicit facts, then
validates both artifacts before writing. A network/validation failure preserves
the previous files. Contributor usernames/UIDs are omitted as unrelated to POI
facts. Refresh does not add new IDs, import into Postgres, call embeddings or
repeat the historical charging discovery queries.

The existing corpus manifests, source reports and production database remain
separate. Package this supplement with the matching backend; do not load
synthetic tests as city records. An older source edit date does not become a
recent factual observation merely because the record was downloaded again.
