# Qadam Astana working agreement

## Project and communication

- The user's S00 request explicitly selects Qadam Astana for this repository.
  The earlier TaskFlow/LinkPulse/NotifyHub portfolio order remains outside this
  repository; do not modify those projects here.
- Communicate with the user in Russian. Write code, identifiers, comments,
  commits, README, API contracts and repository documentation in English.
- Explain simply and report errors, failing checks, uncertainty and unfinished
  work honestly. The user must be able to explain and extend every feature.
- Read active AGENTS.md files, README, docs/task-board.md, relevant code and Git
  status before changes. Existing user work must never be overwritten.
- docs/task-board.md is this project's roadmap (including for workflow commands
  that previously referred to docs/ROADMAP.md).

## Scope and ownership

- Work on only the requested task. One task is one logical reviewable change.
  Stop afterward; do not implement the next stage automatically.
- Sabyrzhan owns root/shared files, contracts/, backend requirements and shared
  dependencies, backend/app/schemas.py, settings.py, openai_client.py,
  repository.py, database/migrations, API, RAG, 2GIS, weather and deployment.
- Damir owns frontend/, all kk/ru/en UI translations, ingestion/, data/ and
  backend/app/services/events/. Do not create or refactor his frontend in S00.
- Sabyrzhan alone changes shared dependencies and contracts. Damir requests
  changes through handoff notes instead of editing those files concurrently.
- Use separate branches/worktrees or clones. Do not change another person's
  active checkout. Check for concurrent changes before staging explicit paths.
- Keep handoffs in docs/handoffs/<TASK-ID>.md: commands, results, contract
  version, dependencies, blockers and next consumer. Never claim delivery or
  acknowledgement from a teammate without evidence.
- Each contributor has 24 active hours. Stage windows: 00 0–1, 01 1–3, 02 3–6,
  03 6–9, 04 9–12, 05 12–16, 06 16–19, 07 19–22, 08 22–24.
- S00 includes GET /api/health by explicit user amendment. It must start without
  OpenAI/2GIS keys, a database connection, or backend/.env. This endpoint is
  removed from S01 scope. Frontend remains Damir's work.

## Product and data rules

- Use React/Vite/TypeScript, FastAPI/Pydantic, Supabase Postgres/PostGIS/pgvector
  and OpenAI Responses. Preserve a compatible existing stack.
- MVP: automated Astana-wide POI corpus, 1–3 single-destination alternatives,
  sources, reasons, estimated visit duration and an action; time, location and
  budget constraints; separate event search. Do not claim complete city coverage
  merely because a source was queried: measure coverage and failures.
- No accounts, GPS history, ticket purchases or multi-stop itineraries.
- Keep unknown facts null/unknown. Provider unavailability is not no_match.
  Do not silently relax user constraints or claim an estimated route is known.
- 2GIS is optional and disabled by default. Enabling runtime API access does not
  grant storage/indexing rights. Do not persist, cache into the corpus, embed or
  index its payloads without a separately documented and reviewed rights basis.
  S00 persistent record validation rejects 2GIS sources. Runtime sources remain
  ephemeral. Do not treat a map key as a server API key.
- Every persistent source needs explicit storage rights; every indexed source
  also needs indexing rights. Retain provenance and source timestamps.
- Fixtures must be clearly synthetic; never load test examples as the real city
  corpus. Keep source content separate from generated explanations.

## Workflow commands (preserved)

- STATUS: read-only report of root, branch, status, recent commits, active
  instructions, last completed/first incomplete task and known failures.
- PLAN <ID>: read-only goal, exact scope/non-goals, files, data flow, database and
  dependency changes, tests, risks, decisions, verification, branch and commit.
- IMPLEMENT <ID>: inspect instructions/roadmap/status/branch/code and ensure
  the task is incomplete; implement only it, add relevant tests, format, run
  checks, review diff; do not commit, push or mark it complete.
- REVIEW <ID>: review uncommitted diff for correctness, scope, errors, security,
  SQL, context/resource handling, concurrency, tests, readability, abstractions,
  unrelated changes, secrets and documentation; fix only task-related issues,
  rerun checks; do not commit or push.
- EXPLAIN <ID>: read-only explanation of actual code, problem, files, flow,
  functions/types, design, failures, tests, five interview Q&As and one exercise.
- COMMIT <ID>: confirm intended scope, format, test, run static checks, review,
  mark only this task complete, verify staged files contain no secrets/local
  env, and create one focused Conventional Commit. Do not push.
- PUSH: push the current branch to origin. Never force-push or merge.
- PR: prepare a PR into main with summary, changes, API/database changes, tests,
  manual verification, limitations and task IDs. Preserve meaningful commits.
- NEXT: read-only selection of the first incomplete task, goal, branch, files,
  tests, checks and commit message. Do not implement it.
- S00's requested shared commit is task-specific authorization for exactly one
  S00 commit after review/checks. It does not authorize a push or later tasks.
- FAST EPIC <FIRST>..<LAST> explicitly permits sequential work and one separate
  checked commit per task in that range, using roadmap messages. Before each
  task inspect state; do not skip checks, create empty/artificial commits,
  implement outside the range, merge or push early. Stop on unrelated existing
  changes, destructive database work, secret exposure, persistent test failures,
  conflicting instructions, possible data loss or a major unplanned design or
  dependency decision. Report tasks, commits, files/packages, migrations,
  endpoints, exact checks, limitations, study topics and suggested PR text.

## Git and dependencies

- Keep main runnable. Use lowercase kebab-case feature branches, such as
  feature/s00-contract-server. Use meaningful Conventional Commits.
- No commit/push without explicit authorization. No empty commits, changed
  authors/dates, force push, published history rewriting, hard reset, amend or
  rebase of published history without an explicit user request.
- Prefer the standard library. Every dependency solves a present problem.
  Explain and get approval before adding an unplanned production dependency or
  replacing an existing library. No Kubernetes, Kafka, AWS, Terraform, gRPC,
  GraphQL, Elasticsearch, Prometheus or Grafana without scope expansion.
- Planned S00 runtime dependencies: FastAPI/Pydantic (HTTP/validation),
  pydantic-settings (env precedence/path loading), uvicorn (ASGI), official
  openai SDK (Responses/embeddings), psycopg binary (read-only DB preflight),
  tzdata (IANA timezone support on Windows). Review dependency updates normally;
  SDK installation does not prove project access to a model.

## Security and verification

- Never commit secrets or local environment files. Maintain a safe .env.example.
  Exclude real env files from Git and Docker contexts at every depth.
- Never log passwords, hashes, JWTs, auth headers, connection URLs, API keys,
  provider exception bodies or raw GPS/query payloads.
- Parameterize SQL, validate inputs, hide internal errors, propagate timeouts,
  clean up resources and never weaken security to pass checks.
- Frontend env: VITE_API_BASE_URL=/api and optional public
  VITE_TWOGIS_MAP_KEY only. Server secrets never use a VITE_ name.
- For Python changes run compile/import checks, pytest, ruff check and ruff
  format --check. Validate fixtures against JSON Schema and Pydantic, and check
  generated-contract drift. Run relevant integration checks for observable HTTP,
  database, migrations, provider or deployment changes. Record real external
  preflight results separately; missing keys/network means not_run.
- For any Go changes retain gofmt, go test ./... and go vet ./... and relevant
  integration checks. Do not introduce Go into this scaffold.
- IMPLEMENT/REVIEW/COMMIT reports include changes, important files, flow, exact
  checks/results, study topics, risks, three interview Q&As and the next task
  without starting it.
