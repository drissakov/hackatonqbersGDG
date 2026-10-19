# Street map follow-up

Replaces the empty coordinate grid with a keyless interactive OpenStreetMap
basemap. Existing MapGL remains available with a genuine public map key; server
keys are never exposed. No dependency, backend API or contract changes.

The map shows streets, start and up to three source coordinates; numbered pins
select destinations. Zoom, drag, keyboard and fit controls are available.
Only visible tiles are requested. Browser cache/referrer and visible attribution
follow https://operations.osmfoundation.org/policies/tiles/; no offline/prefetch.
The route API still returns summaries. No line is guessed; the selected walking
path opens through the documented 2GIS pedestrian directions URL.

Checks: 38 targeted frontend tests in five files; TypeScript, scoped Oxlint,
Prettier, production build and build-integrity passed. No full suite repeated.
Browser QA against the hosted real POI API loaded nine street tiles, selected a
real museum, verified zoom/fit and opened 2GIS with pedestrian mode and real
walking alternatives. Only public QA landmark coordinates were used.

Publication is explicitly authorized: commit/push, PR/merge to main and Render.
