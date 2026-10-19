# Synthetic contract examples

Every `*.test.json` file is **TEST ONLY**. Names, coordinates, durations, prices,
events, sessions, timestamps, permissions and URLs are invented fixtures, not
verified facts about Astana. Content URLs use the reserved `example.invalid`
domain; the synthetic S02 route provenance uses the fixed public API endpoint
only to demonstrate its literal contract. It contains no real provider result.
Never ingest these examples into the production corpus or present them as real
recommendations. Persistent example records and their sources have `is_test=true`;
response examples include a `test_data` warning. Request text is explicitly marked
as test text in kk/ru/en.

`manifest.json` maps every fixture to its JSON Schema. Tests validate both JSON
structure/formats and additional Pydantic invariants. The examples cover nullable
budget, all three locales, all response statuses, a POI, an event, a separate
session, event search and the ingestion result.

The empty responses represent separate scenarios, not the result of executing
the populated example request. `no_match` is only appropriate after a completed
search; `unavailable` means the required service/corpus could not be used;
`unknown` means necessary facts/input were insufficient. No real search is
implemented in S00.
