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
- **`SERVER_TIMESTAMP` used inside `transaction.update()`** — confirm this is
  accepted by the pinned `google-cloud-firestore` version in
  `requirements.txt` before trusting it; some older client versions reject
  sentinels inside transactional writes.
