I have a Python + React project called `vectr_dashboard`. Python backend does the scraping/analysis (`scraper_logic.py`), React frontend is the dashboard (`App.js`, `index.js`, `package.json`). Storage is Firestore, auth is Firebase, LLM is Gemini.

You will do this in TWO PHASES. Do not start Phase 2 until I explicitly say "proceed to phase 2." Show diffs before writing files. Preserve `PROMPT_LIBRARY` structure and keys exactly.

═══════════════════════════════════════════
PHASE 1 — CRITICAL BUG FIXES (safe, minimal)
═══════════════════════════════════════════

## Step 1.0: Read and confirm

Read `scraper_logic.py`, `App.js`, `index.js`, `package.json` in full. List back to me:
- Current signature of `run_scraper_analysis`
- Every place `target_urls` appears
- Every place `fetch_from_reddit_api` and `fetch_from_x_api` are called (should be zero)
- React version and react-scripts version in package.json

Wait for my confirmation before writing any code.

## Step 1.1: Fix `target_urls` never populated
In `run_scraper_analysis`, parse the `sites_str` argument. Support one per line or comma-separated:
- `https://example.com/post` → web scrape
- `reddit:<subreddit>:<keyword1,keyword2>` → Reddit search
- `x:<keyword1,keyword2>` → X recent search
Build a list of `(source_type, source_config)` tuples called `targets`.

## Step 1.2: Wire Reddit and X into the main loop
Dispatch each target to the correct fetcher. Each source produces `(text_content, source_url_for_attribution)`. For Reddit/X use synthetic URLs like `reddit://r/{sub}?q={keywords}`.

## Step 1.3: Fix `parse_multiple_json` nested-JSON bug
Replace the regex approach with `json.JSONDecoder().raw_decode()` in a loop that walks the string, skips whitespace/non-JSON, and accumulates valid objects/arrays. Must handle: single object, array of objects, concatenated objects, nested dicts/lists.

## Step 1.4: Add dedupe
Before writing to Firestore, compute `content_hash = sha256(f"{quote}|{source_url}".encode()).hexdigest()`. Use `db.collection('insights').document(content_hash).set(insight, merge=True)` instead of `.add()`.

## Step 1.5: Add retry / rate-limit handling
Add `tenacity` dependency. Wrap `scrape_website_text`, `extract_info_with_gemini`, `fetch_from_x_api`, `fetch_from_reddit_api` with `@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)`.

## Step 1.6: Gemini schema-enforced output
Reconfigure the Gemini call with `response_mime_type="application/json"` and a `response_schema` requiring an array of `{insight, category, quote}` objects. Then `json.loads(response.text)` directly. Keep `parse_multiple_json` as fallback only.

## Step 1.7: Smoke test
Create `test_scraper_smoke.py` using only `unittest.mock`:
- Mocks scrape/Gemini/Firestore
- Runs `run_scraper_analysis` with mixed sources (1 URL, 1 reddit, 1 x)
- Asserts correct insights persisted, dedupe on re-run, stable content_hash

Run it and paste output.

## Step 1.8: Report
- Files changed + line delta
- Final `run_scraper_analysis` in full
- Assumptions I need to verify
- Anything else broken that's out of scope

STOP HERE. Wait for me to say "proceed to phase 2."

═══════════════════════════════════════════
PHASE 2 — ARCHITECTURAL ADDITIONS
═══════════════════════════════════════════

## Step 2.1: Split raw_content from insights
Introduce a new Firestore collection `raw_content` with `{id, source_type, source_url, text, fetched_at, content_hash}`. Every scrape writes to `raw_content` first (deduped by content_hash of `text + source_url`). Then insights are extracted from `raw_content` docs and reference them via `raw_content_id`. This lets us re-run analysis with better prompts without re-scraping.

Add a function `analyze_raw_content(raw_content_id, analysis_goal)` that reads a raw_content doc, runs Gemini, writes insights. Refactor `run_scraper_analysis` to call fetch → write raw_content → analyze_raw_content in sequence.

## Step 2.2: Version the prompts
Add `"version": <int>` to each entry in `PROMPT_LIBRARY` (start all at 1). Store `prompt_version` and `analysis_goal` on every insight doc. This lets us re-run when a prompt improves and prune stale results by version.

## Step 2.3: Pluggable sources
Create `sources/` package with `base.py` defining a `Source` protocol:
```python
class Source(Protocol):
    def fetch(self, config: dict) -> list[RawContent]: ...
```
Move current fetchers into `sources/web.py`, `sources/reddit.py`, `sources/x.py`. Register in a `SOURCES` dict keyed by type. `run_scraper_analysis` looks up the source class from the dict. This makes adding Quora, Hacker News, Stack Exchange later a single-file change.

Add stub files `sources/hackernews.py` and `sources/quora.py` with `NotImplementedError` and a `TODO` comment describing the intended approach (HN Algolia API for the former, Google `site:quora.com` search + Playwright for the latter). Do NOT implement them yet.

## Step 2.4: Embeddings + similarity
Add `openai` as a dependency (or use Gemini embeddings — pick Gemini for consistency: `models/text-embedding-004`).
- After each insight is written, generate an embedding of the `quote` field and store it on the insight doc as `embedding: [float]` (Firestore supports arrays of numbers up to 20k elements — 768-dim is fine).
- Add a function `find_similar_insights(insight_id, top_k=10)` that fetches all insights of the same `analysis_goal`, computes cosine similarity in Python, returns top_k. Not scalable long-term (Firestore lacks native vector search on free tier), but works fine for the first few thousand insights. Add a TODO note that this should move to Supabase pgvector when volume exceeds ~10k insights.

## Step 2.5: Scheduled runs
Create `scheduled_scan.py` with a `run_scheduled_scans()` function that:
- Reads a Firestore collection `scans` where each doc is `{name, sites_str, analysis_goal, schedule_cron, enabled, last_run_at}`
- Filters to scans whose next fire time has passed (parse the cron with `croniter`)
- Runs each via `run_scraper_analysis`
- Updates `last_run_at`

This function is designed to be invoked by an external scheduler (Cloud Scheduler, GitHub Actions cron, or Vercel Cron hitting a Cloud Function). Add a `main.py` entrypoint that calls it, so `python main.py` triggers all due scans.

## Step 2.6: Frontend upgrades (React side)
In `package.json`:
- The combination `react@19.1.1` + `react-scripts@5.0.1` is broken. Options: migrate to Vite, or downgrade React to `^18.3.1`. Choose **downgrade to React 18.3** (lower-risk since it doesn't require build-tool migration). Update `react` and `react-dom` accordingly.
- Remove `algoliasearch` if not referenced anywhere in the codebase (grep first, confirm, then remove).

In `App.js`, add a new route `/scans` that renders a placeholder `<ScansPage />` component (create stub) — this is where scheduled scan management will live. Do not implement it fully yet.

Create `src/pages/InsightDetail.js`: given an insight ID via route param, show the full insight + a "similar insights" list powered by a new backend endpoint (assume `GET /api/insights/:id/similar` — you don't need to build the backend endpoint, just wire the fetch call and show a TODO comment).

Update the DataGrid on the main dashboard to include:
- Filter chips: by `category`, `analysis_goal`, `source_type`, date range
- A "CSV export" button using the existing MUI DataGrid `GridToolbar` export

## Step 2.7: Update smoke test
Extend `test_scraper_smoke.py` to cover:
- raw_content is written before insights
- prompt_version is stamped on insights
- embedding field is populated (mock the embedding call)
- Pluggable source dispatch works for all three types via the SOURCES registry

Run it. Paste output.

## Step 2.8: Final report
- Full file tree of `sources/` and any new files
- All dependencies added (with pinned versions)
- The exact `run_scraper_analysis` and `analyze_raw_content` function bodies
- Any Firestore index requirements (for queries like "insights where analysis_goal == X order by created_at")
- What I need to do manually: env vars, Firestore rules, dependency installs, npm install after package.json changes

## Rules for both phases
- Show unified diffs before writing files
- Never touch `secret_manager.py` without asking
- Preserve every log message; add new ones don't remove old ones
- Prefer minimal diffs over rewrites
- If any step reveals a deeper problem, stop and describe it — don't quietly work around it
- Pin all new dependency versions
- Every new function needs a one-line docstring
- No `print()` for errors — use the existing `log()` pattern or `logging` module