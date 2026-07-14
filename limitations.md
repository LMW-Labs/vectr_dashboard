# Known limitations (upsert_insight)

Carried forward, not fixed now:

- **Similarity scan is a full-collection-scan per item within `analysis_goal`**
  (same pattern as the existing `find_similar_insights`). Fine at current
  volume; needs Supabase pgvector once a single `analysis_goal` exceeds
  ~10k insights.
- **Case 2 (source_url refresh) does a full `mentions` array read/rewrite**
  rather than `ArrayUnion`, since Firestore can't target-replace one array
  element. Fine at current volume; will be the heavier path if a single
  insight accumulates thousands of mentions.
- **`SERVER_TIMESTAMP` used inside `transaction.update()`** — confirmed working
  against the pinned `google-cloud-firestore==2.11.0` via the emulator (used
  for `last_seen` in `_merge_into_existing_insight`, a top-level field).
  **However, `SERVER_TIMESTAMP` cannot be used inside an array element at
  all** — confirmed this raises `TypeError` immediately, both via `.set()`
  and via `ArrayUnion()`, regardless of transaction. This is why each
  `mentions[]` entry's `seen_at` (added for `compute_trends()`) is a
  client-side `datetime.datetime.now(datetime.timezone.utc)` instead of the
  server sentinel — the only two options for an array-element timestamp are
  client-side `datetime.now()` (clock-skew risk, but works) or omitting it.
- **`compute_trends()` depends on `mentions[].seen_at`**, which only exists
  going forward from this change — any insight docs written before this
  commit have mentions with no `seen_at`, so they're silently excluded from
  both trend windows (never counted, never crash). Verified via emulator
  test. No backfill has been written for pre-existing data.
- **`_merge_into_existing_insight`'s `@firestore.transactional` retry has no
  handling for exhausting its retry cap.** Reproduced against the emulator:
  two real concurrent writers merging into the *same* insight doc fail
  intermittently (~2 of 3 runs in testing) with `ValueError: Failed to
  commit transaction in 5 attempts.` — the Firestore client's built-in
  retry limit, not configurable from this code. The exception propagates
  uncaught up through `upsert_insight` -> `analyze_raw_content` ->
  `run_scraper_analysis`. Unlikely to bite given the pipeline dispatches
  sources sequentially within one run today; would need two concurrent
  `run_scraper_analysis` calls (or a future parallelized dispatch) landing
  on the same insight at the same instant. No retry-with-backoff wrapper
  has been added.
- **`scraper_logic.py` imports the deprecated `google.generativeai` SDK**,
  which now emits `FutureWarning: All support for the google.generativeai
  package has ended` on import (confirmed via `test_scraper_smoke.py` run
  on 2026-07-05). Google's replacement is the `google.genai` package. Not
  urgent — it still works — but should be migrated before Google actually
  pulls support. Touches every `genai.` call site in `scraper_logic.py`
  (model construction, `response_mime_type`/`response_schema` config,
  `generate_embedding`), so budget it as its own task rather than folding
  it into an unrelated change.
