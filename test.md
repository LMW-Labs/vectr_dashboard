# Test coverage to add (upsert_insight)

Extending the existing mocked Firestore / emulator suite:

1. Two insights, same quote/goal, similarity >= 0.93, different subreddits
   -> merge (global tier).
2. Two insights, similarity 0.90-0.93, same subreddit -> merge (borderline
   tier).
3. Two insights, similarity 0.90-0.93, different subreddit -> no merge, two
   docs.
4. Two insights, similarity 0.90-0.93, one or both subreddit=None -> no
   merge (safer default).
5. Same `raw_content_id` reprocessed -> `mention_count` unchanged,
   `mentions[]` unchanged.
6. Same `source_url`, different `raw_content_id` (simulated edit) ->
   `mention_count` unchanged, matching mention updated in place, `mentions[]`
   length unchanged.
7. Genuinely new `source_url` above threshold -> `mention_count` +1, new
   entry appended.
8. Concurrent merge attempts on the same insight (simulate via transaction
   retry) -> no lost updates.
