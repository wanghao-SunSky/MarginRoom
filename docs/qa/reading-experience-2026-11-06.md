# Local reading experience candidate — 2026-11-06

This candidate extends the single-user local edition. The existing homepage,
entry route, bilingual sample essays and provider settings remain in place.
It contains no account system, authentication routes, trial identity or usage
service. New learning data stays in the same local data directory as reading
records. Nothing here publishes a service or includes a real API key.

## Changes

- Continuous reading and shared PDF document rendering; optional section layout,
  automatic visible-reading progress, and manual unread overrides.
- Exact note selection anchors, content-version checks, lightweight underlines,
  and small dismissible reminders from matching earlier questions or notes.
- Optional source-grounded explanation feedback and editable suggested cards;
  cards are saved only after confirmation, with idempotent confirmation IDs.
- Source-bound, language/version/section-cached starter questions; no model call
  for each paragraph or scroll. The original bundled sample essays are retained.
- Anki `.apkg` with templates, stable GUIDs and source links; TSV remains.
- Interrupted answers retain readable fragments; the browser reconnects the
  original run from its cursor. Progress comes from completed tool results.
  Reading-budget stops report checked material and gaps. Invalid source links
  are disabled without dropping readable prose. Raw reply protocols and mixed
  operations remain rejected. Separate model rounds keep paragraph boundaries.

The local feedback endpoint allows one in-flight check, at most ten attempted
checks per rolling 24 hours, and an 80-second request deadline. It uses the
configured local model adapter; there is no identity or cloud quota dependency.
The pre-existing optional canonical export URL setting is preserved without a
configured destination.

## Reproduction and results

Use Python 3.12+ and Node 24 (Node 22.13+ is also declared in the README):

```sh
uv sync --locked --group dev
npm --prefix web ci
uv run pytest -q
npm --prefix web test
npm --prefix web run build
uv run --with anki==26.09.4 python tests/verify_anki_package.py
```

Results on this candidate:

- Python: **169 passed, 1 skipped**. The skip is the existing optional local
  converter check. New coverage includes partial-answer persistence, foreign
  source degradation, finite repair budgets, same-run replay, real progress,
  cross-round paragraph separation, automatic/manual read overrides, anchored
  duplicate text, feedback validation/confirmation, and package structure.
- Frontend: **16 passed**, including selection cancellation, duplicate text,
  history matching, reading exposure and both UI languages.
- TypeScript/Vite: **passed with Node 24**. The initial system Node 22.9 was
  below the supported version and missed an optional native bundler binding;
  reinstalling from the unchanged npm lockfile under Node 24 resolved it.
- Official Anki 26.09.4 Collection/RustBackend: **passed** with disposable
  synthetic notes. Initial import creates two notes/cards; reimport leaves two;
  a newer package updates the same note IDs/GUIDs. Unicode, source href query
  parameters and persistence after closing/reopening were checked.
- No account/authentication/trial modules or UI references are introduced.
  The candidate has no environment file, model credentials, user database,
  collection, private screenshot or private QA record. Homepage and entry
  source files are unchanged.

Old assertions that required invalid citations to fail the whole answer were
updated to check readable degradation. Their foreign-document/malformed/mixed
operation cases remain present. Partial text is now asserted as retained while
its run remains failed; it is not treated as a completed answer. Existing
canonical export URL tests remain unchanged.

## Limits

Desktop/mobile Anki GUI import, clicking exported source links, real iPhone or
iPad interaction, and PDF touch/zoom selection were **not tested** here. The
Anki check exercises the official engine rather than the GUI and uses packages
with a later modification timestamp for update validation. Same-second exports
are not claimed to always overwrite a previous import.

Feedback shape and exact source quotations are validated, but these checks do
not establish the model's pedagogical correctness or measure long-term mastery.
No live-model quality result is claimed. No in-app spaced-repetition scheduler
is included. Unknown old note positions, changed documents, image-only PDF pages
and incompatible text-layer layouts are not forcibly highlighted.

Existing pytest/TestClient deprecation warnings and the frontend large-chunk
notice remain; this change does not upgrade unrelated test infrastructure or
redesign the reader's bundle layout.
