# upsert_insight() handoff spec

Context: implementing `upsert_insight()` to replace the exact-hash dedup in
`analyze_raw_content()` (`scraper_logic.py`). Adds semantic similarity merging
with mention-level dedup so reprocessing doesn't inflate counts.

Files touched: `scraper_logic.py` only.

## 1. `write_raw_content()` — add `subreddit` param

```python
def write_raw_content(source_type, source_url, text, subreddit=None):
    """Writes a raw_content doc deduped by hash of text+source_url, returning the doc id (content_hash)."""
    content_hash = hashlib.sha256(f"{text}|{source_url}".encode()).hexdigest()
    db = firestore.Client()
    db.collection('raw_content').document(content_hash).set({
        'source_type': source_type,
        'source_url': source_url,
        'text': text,
        'subreddit': subreddit,
        'fetched_at': firestore.SERVER_TIMESTAMP,
        'content_hash': content_hash,
    }, merge=True)
    return content_hash
```

Call site in `run_scraper_analysis()` (where `write_raw_content` is called)
passes `subreddit=raw_item.get('subreddit')`. `sources/reddit.py`'s
`RedditSource.fetch()` emits `subreddit` in each raw_item dict.

## 2. `analyze_raw_content()` — carry subreddit onto insight, delegate to upsert_insight

```python
def analyze_raw_content(raw_content_id, analysis_goal):
    db = firestore.Client()
    raw_doc = db.collection('raw_content').document(raw_content_id).get()
    if not raw_doc.exists:
        raise ValueError(f"raw_content document {raw_content_id} not found")
    raw = raw_doc.to_dict()

    goal_details = PROMPT_LIBRARY.get(analysis_goal)
    if not goal_details:
        raise ValueError(f"Invalid analysis goal '{analysis_goal}'")

    prompt_version = goal_details.get('version', 1)
    extracted_info_json = extract_info_with_gemini(raw['text'], goal_details['prompt'])

    try:
        data = json.loads(extracted_info_json)
    except json.JSONDecodeError:
        data = parse_multiple_json(extracted_info_json)
    if isinstance(data, dict):
        data = [data]

    results = []
    for item in data:
        item['source_url'] = raw['source_url']
        item['source_type'] = raw['source_type']
        item['subreddit'] = raw.get('subreddit')
        item['raw_content_id'] = raw_content_id
        item['analysis_goal'] = analysis_goal
        item['prompt_version'] = prompt_version
        item['embedding'] = generate_embedding(item.get('quote', ''))

        insight_id = upsert_insight(db, item)
        results.append(insight_id)

    return results
```

**Breaking change:** return value is now a list of insight doc IDs (strings),
not dicts.

> Applied deviation: the actual implementation kept the Step 1
> schema-enforced call (`_build_response_schema` + 3-arg
> `extract_info_with_gemini(raw['text'], goal_details['prompt'], response_schema)`)
> instead of the 2-arg call shown above, which would have regressed the
> goal-specific Gemini schema and crashed (`response_schema` is a required
> positional arg). Confirmed safe: no caller of `analyze_raw_content()`
> consumes the old dict-list return value — `run_scraper_analysis` only does
> `len(all_results)`, and `backend.py`'s `/api/analyze` re-queries Firestore
> separately instead of using the return value directly.

## 3. `upsert_insight()` and helpers — new code

```python
GLOBAL_MERGE_THRESHOLD = 0.93
BORDERLINE_MERGE_THRESHOLD = 0.90


def upsert_insight(db, item):
    """
    Finds the best-matching existing insight for `item` within the same
    analysis_goal and either merges into it or creates a new insight doc.

    Merge rule:
      similarity >= 0.93                            -> merge globally
      0.90 <= similarity < 0.93 and subreddit match -> merge (borderline)
      otherwise                                     -> new insight

    subreddit is None for non-Reddit sources; None never satisfies the
    borderline tie-breaker (treated as "no match" -- safer default).

    Mention-level dedup (prevents reprocessing from inflating mention_count):
      - same raw_content_id already in mentions[]  -> exact reprocess, full no-op
      - different raw_content_id, same source_url  -> refresh that mention in
                                                        place, no count change
      - neither matches                            -> genuinely new mention,
                                                        append + increment

    Returns the doc ID of the insight that was created or updated.
    """
    embedding = item.get('embedding')
    analysis_goal = item['analysis_goal']
    subreddit = item.get('subreddit')
    raw_content_id = item.get('raw_content_id')

    best_match_id = None
    best_score = 0.0
    best_match_data = None

    if embedding:
        candidates = db.collection('insights').where(
            filter=firestore.FieldFilter('analysis_goal', '==', analysis_goal)
        ).stream()

        for doc in candidates:
            data = doc.to_dict()
            candidate_embedding = data.get('embedding')
            if not candidate_embedding:
                continue
            score = _cosine_similarity(embedding, candidate_embedding)

            is_global_match = score >= GLOBAL_MERGE_THRESHOLD
            is_borderline_match = (
                BORDERLINE_MERGE_THRESHOLD <= score < GLOBAL_MERGE_THRESHOLD
                and subreddit is not None
                and data.get('subreddit') == subreddit
            )

            if (is_global_match or is_borderline_match) and score > best_score:
                best_score = score
                best_match_id = doc.id
                best_match_data = data

    if best_match_id:
        existing_mentions = best_match_data.get('mentions', [])

        # Exact reprocess of the same fetched payload -> full no-op.
        already_exact_reprocess = any(
            m.get('raw_content_id') == raw_content_id
            for m in existing_mentions
        )
        if already_exact_reprocess:
            return best_match_id

        _merge_into_existing_insight(db, best_match_id, item, existing_mentions)
        return best_match_id
    else:
        return _create_new_insight(db, item)


def _merge_into_existing_insight(db, insight_id, item, existing_mentions):
    """Atomically merges a matched item into an existing insight doc."""
    doc_ref = db.collection('insights').document(insight_id)
    raw_content_id = item.get('raw_content_id')
    source_url = item.get('source_url')

    new_mention = {
        'quote': item.get('quote', ''),
        'source_url': source_url,
        'source_type': item.get('source_type'),
        'subreddit': item.get('subreddit'),
        'raw_content_id': raw_content_id,
    }

    # Edited/refetched version of an already-recorded source_url -> refresh
    # that mention in place, don't count it as a new occurrence.
    existing_url_match = next(
        (m for m in existing_mentions if m.get('source_url') == source_url), None
    )

    @firestore.transactional
    def _do_merge(transaction):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False

        if existing_url_match:
            current_mentions = snapshot.get('mentions') or []
            updated_mentions = [
                new_mention if m.get('source_url') == source_url else m
                for m in current_mentions
            ]
            transaction.update(doc_ref, {'mentions': updated_mentions})
        else:
            transaction.update(doc_ref, {
                'mention_count': firestore.Increment(1),
                'mentions': firestore.ArrayUnion([new_mention]),
                'last_seen': firestore.SERVER_TIMESTAMP,
            })
        return True

    transaction = db.transaction()
    merged = _do_merge(transaction)
    if not merged:
        # Doc was deleted between the query and the transaction.
        _create_new_insight(db, item)


def _create_new_insight(db, item):
    """Writes a brand-new insight doc with merge fields initialized."""
    content_hash = hashlib.sha256(
        f"{item.get('quote', '')}|{item.get('source_url', '')}".encode()
    ).hexdigest()

    doc = dict(item)
    doc['content_hash'] = content_hash
    doc['mention_count'] = 1
    doc['mentions'] = [{
        'quote': item.get('quote', ''),
        'source_url': item.get('source_url'),
        'source_type': item.get('source_type'),
        'subreddit': item.get('subreddit'),
        'raw_content_id': item.get('raw_content_id'),
    }]
    doc['first_seen'] = firestore.SERVER_TIMESTAMP
    doc['last_seen'] = firestore.SERVER_TIMESTAMP
    doc['timestamp'] = firestore.SERVER_TIMESTAMP  # backward compat with existing queries

    db.collection('insights').document(content_hash).set(doc, merge=True)
    return content_hash
```

> Applied deviation: `db.collection('insights').where(filter=firestore.FieldFilter(...))`
> was replaced with the positional form `db.collection('insights').where('analysis_goal', '==', analysis_goal)`.
> `firestore.FieldFilter` does not exist in `google-cloud-firestore==2.11.0`,
> the version pinned in `requirements.txt` (it was added in a later release).
> Verified directly against the pinned version before writing this file. The
> pre-existing `find_similar_insights()` (Phase 2, embeddings) had the same
> bug and was never caught because no test exercises it — fixed the same way
> while in here.

## Known follow-up (not yet done)

- `test_scraper_smoke.py` asserts on the old `.document(hash).set(item, merge=True)`
  write pattern and needs a rewrite to match the new upsert/transaction-based
  writes.
- `GLOBAL_MERGE_THRESHOLD` / `BORDERLINE_MERGE_THRESHOLD` are hardcoded here;
  `settingsUI.md` already lists a `SIMILARITY_THRESHOLD` settings-UI control
  as a future TODO — these two hardcoded constants are the code this control
  would eventually need to point at.
