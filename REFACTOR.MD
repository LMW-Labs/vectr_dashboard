Vectr Dashboard — Claude Code Master Handoff
Project: vectr_dashboard
Owner: Austin Wyrick
Stack: Python backend (scraper_logic.py) + React frontend (App.js, index.js, package.json)
Storage: Firestore (migrating to Supabase in Phase 3)
Auth: Firebase
LLM: Google Gemini (gemini-1.5-flash-latest)
Deployment target: Vercel (frontend + serverless), Cloud Run or Vercel Cron (worker)

Strategic context (read this before writing any code)
Vectr is being reframed. It started as a general-purpose pain-point scraper. It is now being pointed at a specific problem: surfacing the highest-odds unnamed niche for Austin to build a product for, at the intersection of his existing skills:

Logistics & inventory operations

Hardware / sensor wiring

Cloud backend (Supabase, Vercel, TypeScript)

Sports coaching tools (existing domain trust — he has already built for coaches)

The tool must eventually be agent-callable so autonomous agents can drive research → clustering → report generation → landing page creation without human orchestration. Everything is built with that endgame in mind.

The niche listening strategy (drives what we build)
Vectr will ingest from 7 Tier-1 target zones simultaneously for 2–3 weeks. Data picks the niche, not gut.

Tier-1 source zones (build for these first)
Reverse logistics / liquidation resellers

Subreddits: AmazonSeller, FulfillmentByAmazon, logistics, warehouse, AmazonReturnPallets, Flipping, liquidation, FBAmazon

Route-based rolling inventory operators

Subreddits: propane, vending, smallbusiness (filtered), Entrepreneur (filtered)

Coaching persona A (independent skills trainers)

Subreddits: QBCoach, basketballcoach, soccercoaching, HittingCoach

Facebook groups via Google site:facebook.com search

Coaching persona F (small facility owners)

Subreddits: BattingCages, gyms, IndoorSoccer, plus smallbusiness posts mentioning "facility"

Competitor review mining (this is the gold mine)

G2 + Capterra 1–3 star reviews for: TeamSnap, Hudl, Upper Hand, Fishbowl, Cin7, ShipHero, ShipBob, TeamBuildr

Small/mid 3PL and Amazon FBA prep centers

Same as zone 1 plus LinkedIn Warehouse Nerds group discussions

Indie Hackers + Hacker News Ask-HN

Filtered for logistics, inventory, coaching keywords

Two new prompt goals to add to PROMPT_LIBRARY
Beyond the existing 15 goals, add these — they are the highest-signal extractions for niche discovery:

python
'willingness_to_pay_signals': {
    "prompt": """You are a market analyst hunting for revenue signals. Scan the text for any indication a person or business would spend money to solve a problem. Look for phrases like: "I would pay", "someone should build", "I'd give money for", "why doesn't X exist", "I've been looking for", "willing to pay $X for", "shut up and take my money". For each signal, extract: 1. "insight": what they would pay for. 2. "category": problem area (e.g., "Scheduling", "Inventory", "Reporting", "Compliance"). 3. "quote": the direct sentence. 4. "estimated_wtp_tier": "unknown" | "low_under_50" | "mid_50_to_500" | "high_500_plus" based on context. Return a list of JSON objects.""",
    "columns": [{'name': 'Would Pay For', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'WTP Tier', 'id': 'estimated_wtp_tier'}, {'name': 'Source URL', 'id': 'source_url'}],
    "version": 1
},
'tool_switching_signals': {
    "prompt": """You are a competitive intelligence analyst. Find any mention of switching between tools, abandoning a tool, or seeking alternatives. Look for phrases like: "we switched from X to Y because", "X is killing us", "looking for alternative to X", "X used to be good but", "moving off of X", "X is the worst". For each signal, extract: 1. "insight": summary of the switch or search. 2. "category": always "Tool Switching". 3. "quote": the direct sentence. 4. "from_tool": the tool being left (or null). 5. "to_tool": the tool being adopted (or null). 6. "reason": the stated reason for the switch. Return a list of JSON objects.""",
    "columns": [{'name': 'Switching Signal', 'id': 'insight'}, {'name': 'From Tool', 'id': 'from_tool'}, {'name': 'To Tool', 'id': 'to_tool'}, {'name': 'Reason', 'id': 'reason'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}],
    "version": 1
}
What exists today (state of the code)
scraper_logic.py — Python scraper + Gemini extractor with 15-goal PROMPT_LIBRARY. Has 6 known critical bugs (see Phase 1).

App.js — React root with Firebase auth + MUI theme + BrowserRouter.

index.js — Standard React 18/19 entry point.

package.json — React 19.1.1 + react-scripts 5.0.1 (known-broken combo; downgrade to React 18.3 in Phase 2).

Firestore collection insights holds output.

Reddit (PRAW), X API (tweepy), and website scraping are all implemented BUT Reddit and X are never called because target_urls is never populated (Bug #1).

Build plan — three phases, four sub-phases in Phase 3
Execute in order. Do NOT proceed between phases without explicit approval from Austin. Show unified diffs before writing files. Preserve PROMPT_LIBRARY keys.

═══════════════════════════════════════════

PHASE 1 — Critical bug fixes (safe, minimal)
1.0 Read and confirm
Read scraper_logic.py, App.js, index.js, package.json in full. Report:

Current signature of run_scraper_analysis

Every place target_urls appears

Every place fetch_from_reddit_api and fetch_from_x_api are called (should be zero)

React and react-scripts versions
Wait for confirmation before writing code.

1.1 Fix target_urls never populated
Parse sites_str arg. Support one-per-line or comma-separated:

https://example.com/post → web scrape

reddit:<subreddit>:<keyword1,keyword2> → Reddit search

x:<keyword1,keyword2> → X recent search
Build targets: list[tuple[str, dict]].

1.2 Wire Reddit + X into main loop
Dispatch each target to the correct fetcher. Each source produces (text_content, source_url_for_attribution). Synthetic URLs like reddit://r/{sub}?q={keywords} for non-URL sources.

1.3 Fix parse_multiple_json nested-JSON bug
Replace the regex r'\{.*?\}' (non-greedy, breaks nested objects) with json.JSONDecoder().raw_decode() in a loop. Must handle single object, array of objects, concatenated objects, and nested dicts/lists.

1.4 Add dedupe
Before writing insights: content_hash = sha256(f"{quote}|{source_url}".encode()).hexdigest(). Use db.collection('insights').document(content_hash).set(insight, merge=True) instead of .add().

1.5 Add retry / rate-limit handling
Add tenacity (pinned). Wrap scrape_website_text, extract_info_with_gemini, fetch_from_x_api, fetch_from_reddit_api with @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True).

1.6 Gemini schema-enforced output
Configure Gemini with response_mime_type="application/json" and a response_schema requiring array of {insight, category, quote}. Use json.loads(response.text) directly. Keep parse_multiple_json as fallback only.

1.7 Add the two new prompt goals
Add willingness_to_pay_signals and tool_switching_signals to PROMPT_LIBRARY exactly as specified in the "Strategic context" section above.

1.8 Smoke test
Create test_scraper_smoke.py using only unittest.mock. Mock scrape/Gemini/Firestore. Run run_scraper_analysis with mixed sources (1 URL + 1 reddit + 1 x). Assert correct persistence, dedupe on re-run, stable content_hash, and the two new prompts work. Run it. Paste output.

1.9 Report
Files changed + line delta

Final run_scraper_analysis in full

Assumptions to verify

Anything else broken but out of scope

STOP. Wait for "proceed to phase 2".

═══════════════════════════════════════════

PHASE 2 — Architectural additions
2.1 Split raw_content from insights
New Firestore collection raw_content {id, source_type, source_url, text, fetched_at, content_hash}. Every scrape writes there first. Insights reference raw_content_id. Enables re-running analysis with better prompts without re-scraping.

Add analyze_raw_content(raw_content_id, analysis_goal). Refactor run_scraper_analysis to: fetch → write raw_content → analyze_raw_content.

2.2 Version the prompts
Add "version": <int> to each PROMPT_LIBRARY entry (start all at 1). Store prompt_version and analysis_goal on every insight doc.

2.3 Pluggable sources
Create sources/ package with base.py defining a Source protocol. Move current fetchers to sources/web.py, sources/reddit.py, sources/x.py. Register in SOURCES dict. run_scraper_analysis looks up source class from dict.

Add stub files sources/hackernews.py (uses HN Algolia API — free, no key), sources/quora.py (Google site:quora.com search + Playwright), sources/stackexchange.py (free API), sources/g2_reviews.py (Playwright — review mining is a Tier-1 source), sources/capterra_reviews.py (Playwright). All with NotImplementedError and TODO comments describing approach. Do NOT implement yet.

2.4 Embeddings + similarity
Use Gemini embeddings (models/text-embedding-004, 768-dim). After each insight written, generate embedding of quote field, store as embedding: [float] on insight doc.

Add find_similar_insights(insight_id, top_k=10) — fetch all insights of same analysis_goal, compute cosine similarity in Python, return top_k. Add TODO to move to Supabase pgvector when volume >10k insights.

2.5 Scheduled runs
Create scheduled_scan.py with run_scheduled_scans():

Read Firestore scans collection: {name, sites_str, analysis_goal, schedule_cron, enabled, last_run_at}

Filter to scans whose next fire time has passed (use croniter)

Run each via run_scraper_analysis

Update last_run_at, last_status, last_error

Add main.py entrypoint. Designed to be invoked by Vercel Cron or Cloud Scheduler.

2.6 Seed the Tier-1 scans
Create scripts/seed_scans.py that inserts the following scans into Firestore. All target analysis_goal='willingness_to_pay_signals' initially, with a companion scan for pain_points on the same targets. Schedule all as 0 */6 * * * (every 6 hours):

text
Tier-1 scan targets (seed as scan rows):

# Reverse logistics
reddit:AmazonSeller:returns,liquidation,pallet
reddit:FulfillmentByAmazon:returns,damaged,refund
reddit:AmazonReturnPallets:profitable,tool,scanner,inventory
reddit:Flipping:inventory,tool,software,tracking
reddit:liquidation:inventory,software,scanner

# Route-based rolling inventory
reddit:propane:route,dispatch,inventory,delivery
reddit:vending:route,inventory,machine,management

# Coaching persona A
reddit:QBCoach:tool,software,scheduling,parent
reddit:basketballcoach:tool,software,scheduling,parent
reddit:soccercoaching:tool,software,scheduling,parent
reddit:HittingCoach:tool,software,scheduling,parent

# Coaching persona F
reddit:BattingCages:booking,software,scheduling
reddit:gyms:booking,software,membership
reddit:IndoorSoccer:booking,software,facility

# Small/mid 3PL and prep
reddit:logistics:inventory,software,wms,3pl
reddit:warehouse:inventory,scanner,software

# General SMB signal
reddit:smallbusiness:inventory,scheduling,software
reddit:Entrepreneur:inventory,scheduling,software
2.7 Frontend upgrades
In package.json:

Downgrade react and react-dom to ^18.3.1 (fixes react-scripts@5 incompatibility)

Grep for algoliasearch usage — if none, remove it

In App.js, add route /scans rendering <ScansPage /> (stub for now).

Create src/pages/InsightDetail.js — insight ID via route param, shows insight + "similar insights" list via fetch to /api/insights/:id/similar (backend not built yet, wire fetch and TODO).

Update DataGrid to include filter chips (category, analysis_goal, source_type, date range) + CSV export via MUI GridToolbar.

2.8 Extend smoke test
Assert: raw_content written before insights, prompt_version stamped, embedding populated (mock the embed call), pluggable source dispatch works for all three source types via SOURCES registry.

2.9 Report
File tree of sources/

All deps added (pinned versions)

Full bodies of run_scraper_analysis and analyze_raw_content

Firestore composite index requirements

Manual steps: env vars, Firestore rules, npm install, python -m scripts.seed_scans

STOP. Wait for "proceed to phase 3.1".

═══════════════════════════════════════════

PHASE 3.1 — Supabase schema + dual-write
3.1.1 Read state
Read current scraper_logic.py, sources/*.py, scheduled_scan.py, Firestore-touching frontend. Confirm understanding of where raw_content, insights, embeddings, scans live. Wait for confirmation.

3.1.2 Supabase schema
Create supabase/migrations/0001_init.sql:

sql
create extension if not exists vector;
create extension if not exists pgcrypto;

create table sources (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('web','reddit','x','hackernews','quora','stackexchange','g2_reviews','capterra_reviews')),
  config jsonb not null,
  created_at timestamptz default now()
);

create table raw_content (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id) on delete set null,
  source_type text not null,
  source_url text not null,
  external_id text,
  author text,
  text text not null,
  content_hash text not null unique,
  raw_json jsonb,
  fetched_at timestamptz default now()
);
create index on raw_content (source_type, fetched_at desc);

create table insights (
  id uuid primary key default gen_random_uuid(),
  raw_content_id uuid references raw_content(id) on delete cascade,
  analysis_goal text not null,
  prompt_version int not null,
  insight text not null,
  category text,
  quote text not null,
  source_url text,
  content_hash text not null,
  embedding vector(768),
  extra jsonb,
  created_at timestamptz default now(),
  unique (content_hash, analysis_goal, prompt_version)
);
create index on insights (analysis_goal, created_at desc);
create index on insights using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table scans (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  sites_str text not null,
  analysis_goal text not null,
  schedule_cron text not null,
  enabled boolean default true,
  last_run_at timestamptz,
  last_status text,
  last_error text,
  created_at timestamptz default now()
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  payload jsonb not null,
  status text not null default 'pending' check (status in ('pending','running','succeeded','failed','cancelled')),
  attempts int default 0,
  max_attempts int default 3,
  scheduled_for timestamptz default now(),
  started_at timestamptz,
  finished_at timestamptz,
  result jsonb,
  error text,
  created_at timestamptz default now()
);
create index on jobs (status, scheduled_for) where status in ('pending','running');

create table job_logs (
  id bigserial primary key,
  job_id uuid references jobs(id) on delete cascade,
  level text not null,
  message text not null,
  ts timestamptz default now()
);
Print SQL and wait for approval before saving.

3.1.3 Supabase client wrapper
Create db/supabase_client.py. Read SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY via get_secret(). Cached get_client(). pgvector_available() health check. Pin supabase>=2.5,<3 and psycopg[binary].

3.1.4 Dual-write mode
Env var STORAGE_MODE = firestore | supabase | dual. Default dual.

In dual: Firestore first (authoritative), then Supabase. Supabase failures log only. Firestore failures fail the run.

Repository class in db/repository.py: write_raw_content, write_insight, read_scans_due, update_scan_status, find_similar_insights.

Refactor everything to go through Repository — never Firestore/Supabase directly.

3.1.5 Backfill script
Create scripts/backfill_firestore_to_supabase.py. Read all raw_content + insights from Firestore, write to Supabase (Supabase-only mode). Idempotent via content_hash ON CONFLICT. Report read/written/skipped/errored counts. Do NOT auto-run.

3.1.6 Verification
Extend smoke test with StubRepository. Assert dual-mode writes both stubs and Supabase failures don't fail runs.

STOP. Wait for "proceed to 3.2".

═══════════════════════════════════════════

PHASE 3.2 — Cutover to Supabase
3.2.1
After Austin confirms backfill ran and row counts match:

Default STORAGE_MODE → supabase

Rewrite find_similar_insights to use Postgres <=> cosine distance operator

Keep Firestore path gated behind STORAGE_MODE=firestore for emergency rollback

3.2.2 Frontend cutover
Replace Firestore SDK reads with API layer. Create Vercel serverless functions:

GET /api/insights — filters: analysis_goal, category, source_type, date_from, date_to, cursor

GET /api/insights/:id — insight + raw_content join

GET /api/insights/:id/similar?top_k=10 — pgvector similarity

GET/POST/PATCH/DELETE /api/scans[/:id]

GET /api/jobs?status=...

Server-side uses Supabase service role key. Client uses anon key only. Migration 0002_rls.sql enables RLS: authenticated reads, service-role-only writes.

Update App.js, DashboardLayout, pages to use fetch. Firebase Auth stays — validate Firebase ID token server-side via Firebase Admin, then query Supabase.

3.2.3 Tests
Integration tests per API route using Supabase test schema. Skip if SUPABASE_TEST_URL unset.

STOP. Wait for "proceed to 3.3".

═══════════════════════════════════════════

PHASE 3.3 — Job runner (the agent hook)
3.3.1 Job kinds
jobs/kinds.py enum:

ingest_source — payload {source_type, config} → writes raw_content

analyze_raw_content — payload {raw_content_id, analysis_goal, prompt_version} → writes insights

embed_insight — payload {insight_id} → writes embedding

cluster_insights — payload {analysis_goal, since, min_cluster_size} → writes clusters

run_scan — payload {scan_id} → orchestrates ingest → analyze → embed

generate_report — payload {analysis_goal, since, format} → stores in Supabase Storage reports bucket

Add migration 0003_clusters.sql: clusters(id, analysis_goal, label, centroid vector(768), created_at) + cluster_members(cluster_id, insight_id).

Each kind = class in jobs/handlers/ implementing JobHandler protocol. Register in jobs/registry.py.

3.3.2 Worker
jobs/worker.py with run_worker(max_jobs=10, poll_seconds=5):

Select pending jobs with SELECT ... FOR UPDATE SKIP LOCKED (raw psycopg SQL)

Set running, dispatch to handler

On success: succeeded + result. On failure: increment attempts, exponential backoff, or fail

Write to job_logs throughout

SIGTERM: finish current, exit clean

jobs/enqueue.py: enqueue(kind, payload, scheduled_for=None) -> job_id.

Refactor scheduled_scan.py to enqueue run_scan jobs instead of running inline.

3.3.3 Worker deployment
Two paths, doc when to use:

Vercel Cron hits /api/worker/tick every 60s, runs run_worker(max_jobs=5). Ship this now. Good for <1000 jobs/day.

Long-running worker on Cloud Run / Railway. Create Dockerfile.worker but don't deploy.

3.3.4 Frontend for jobs
/jobs route: recent jobs + status + kind + duration + retries + filter. Click through to job_logs. Retry button on failed jobs → POST /api/jobs/:id/retry.

3.3.5 Tests
Fake handlers (succeeds, deterministic-fail, fail-twice-succeed). Assert backoff, max_attempts.

STOP. Wait for "proceed to 3.4".

═══════════════════════════════════════════

PHASE 3.4 — Agent interface
3.4.1 Tool schema
agent/tools.py — OpenAI/Anthropic function-calling format:

list_analysis_goals() — PROMPT_LIBRARY keys

create_scan(name, sites_str, analysis_goal, schedule_cron)

run_scan_now(scan_id | name) → job_id

wait_for_job(job_id, timeout_s=300)

query_insights(analysis_goal, category?, since?, limit?, semantic_query?) — with pgvector for semantic

cluster_insights_now(analysis_goal, since, min_cluster_size) — waits, returns clusters + reps

generate_report(analysis_goal, since, format) → signed URL

propose_new_scan(topic_hint) — Gemini suggests config, returns proposal only

JSON schemas + natural-language descriptions per tool.

3.4.2 MCP server (optional, recommended)
agent/mcp_server.py — MCP protocol so Claude Desktop / Cursor / Claude Code plug in as tool provider. Follow MCP Python SDK. Stub + TODO if SDK unavailable.

3.4.3 HTTP endpoint
POST /api/agent/invoke — {tool_name, arguments}, Firebase ID token required.

3.4.4 Example agent
examples/agent_demo.py — Anthropic Python SDK. System prompt: "market research agent, discover pain points, return ranked top 10." Tools: 3.4.1. User: "Find the top 10 pain points that liquidation pallet resellers are discussing right now." Runs tool loop to final answer. Reads keys from env.

3.4.5 Final report
Mermaid architecture diagram

README section: "Running vectr as an agent-driven platform" + example commands

Every env var, grouped by phase

Known limits (Firestore rollback, pgvector index, worker throughput on Vercel)

Phase 4 candidates

═══════════════════════════════════════════

Global rules for all phases
Show unified diffs before writing files

Never touch secret_manager.py without asking

Preserve every log message; add new ones don't remove old ones

Prefer minimal diffs over rewrites

If a step reveals a deeper problem, stop and describe it — don't quietly work around

Pin all new dependency versions

New functions get a one-line docstring

New code uses type hints

No print() for errors — use log() pattern or logging module

Every migration is numbered and reversible (-- down section)

No secrets in code — all via get_secret() or env

Never break existing behavior — dual-run until cutover proven

═══════════════════════════════════════════

What Austin should do manually (between phases)
After Phase 1:

Run python -c "from scraper_logic import run_scraper_analysis; ..." with one real target to sanity-check end-to-end.

After Phase 2:

python -m scripts.seed_scans to load the Tier-1 targets

Set up Vercel Cron (or Cloud Scheduler) to hit main.py every 6 hours

npm install to pick up React 18.3 downgrade

Let it run for 14 days to accumulate data

Review the dashboard to identify the winning niche

After Phase 3.1:

Create Supabase project, run migration

Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY secrets

Run backfill script manually, compare row counts

After Phase 3.2:

Verify all API routes work with Firebase auth

Toggle STORAGE_MODE=supabase

After Phase 3.3:

Enable Vercel Cron for /api/worker/tick

Watch /jobs for anything stuck

After Phase 3.4:

Run examples/agent_demo.py to see the payoff — an agent driving vectr end-to-end.

═══════════════════════════════════════════

The endgame
When Phase 3.4 completes, Austin can say to an agent:

"Find me the top 10 pain points that liquidation pallet resellers are discussing right now, cluster them by theme, tell me which cluster has the strongest willingness-to-pay signals, draft landing-page copy for the winning idea, and email me the report."

And it runs — end to end — without human orchestration. That is the tool that makes every future client project 10x faster and unlocks the "agents doing the work" future Austin described at the start.