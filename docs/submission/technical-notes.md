# Backend release notes

Date: 2026-10-19. Baseline: main `2ba4c4f`, including merged event fix and D05.
Scope: critical backend/demo checks, minimal correctness fixes and existing deployment.

- API contract remains 1.3.0. No endpoint/schema, migration or dependency changes.
- Real POI retrieval uses the existing permitted corpus and lexical/vector index; responses contain at most three independent alternatives and source/provenance.
- Explicit time, budget and return constraints remain deterministic. Missing route/hours/price facts never become confirmed values.
- D05 BQ-01/02 follow-up blocks unsupported child/age and charging requirements conservatively before providers. BQ-03 cosmetics are deferred.
- The embedding loader accepts the importer's unchanged POI contract 1.3.0 while preserving checksum, rights and content/model validation.
- Weather and a broad evaluation suite are excluded. No production reimport, migrations or re-embedding was needed for the already populated demo database.

Verification and deployment results are recorded below after execution. Historical
D05 provider failures remain historical; current hosted checks are separate.

## Verification

- Hosted critical path: 9/9 checks passed. Health/coverage returned 200; coverage showed 985 real POIs, 985 embeddings and zero test POIs.
- kk/ru/en returned 3/2/3 sourced OSM alternatives with known walking totals. Unknown hours/prices remained conditional; a one-minute request returned no_match.
- Direct walking checks: outbound-only 32 minutes; independent outbound/return total 63 minutes. Both response contracts validated.
- Events returned HTTP 200 partial, one linked listing and one dated session. No ticket/end guarantee was introduced.
- Targeted Python checks: 116 constraint/service regressions, 5 export-manifest checks and 8 existing failure/unknown/return checks passed. Full repository suites were not run.
- Production frontend build, build-integrity and shared-contract checks passed. Docker build and keyless container health/SPA passed; missing OpenAI returned structured 503/unavailable. A final cached image rebuild includes both fixes.
- Provider timeout/refusal fallback was checked with deterministic doubles; live production credentials were not disabled. Local OpenAI network access is not required for the hosted demo.

Deployment uses the existing Render service and the isolated release branch.
The final deployment outcome and post-deploy health are reported separately.
