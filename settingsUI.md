Pipeline/scraping settings:

Target sources list (subreddits, URLs, keywords) — editable
Scrape frequency/schedule (cron interval)
Analysis goal(s) active per run (pain_points, feature_requests, etc.)
Rate limits per source (avoid hammering Reddit API)

Extraction/AI settings:

Model selection (Gemini version/tier)
Prompt version per goal (already versioned in PROMPT_LIBRARY)
Temperature/token limits if exposed

Dedup/trend settings:

SIMILARITY_THRESHOLD (currently hardcoded, should be adjustable)
Trend window size (currently 7-day, hardcoded)
Rising/falling multiplier thresholds (1.2x/0.8x, hardcoded)

Publishing settings:

Auto-publish toggle vs. manual review queue
Minimum mention_count/trend state required before publish eligibility
Category → affiliate_category mapping rules

Cost/limits:

API spend cap / kill switch
Max insights processed per run
Max sites scraped per run

Access/auth:

Admin dashboard auth (exists, unclear if enforced)
API key for public endpoints (flagged missing earlier, still missing)