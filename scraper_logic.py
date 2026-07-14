# scraper_logic.py
import os
import hashlib
import logging
import math
import json
import time
import datetime
import google.generativeai as genai
from google.cloud import firestore
from tenacity import retry, stop_after_attempt, wait_exponential

from sources import SOURCES

logger = logging.getLogger(__name__)

RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)

EMBEDDING_MODEL = 'models/text-embedding-004'

def _build_response_schema(columns):
    """Builds a Gemini JSON response schema (array of objects) from a PROMPT_LIBRARY columns list.

    Derived per-goal (instead of a single fixed {insight, category, quote} schema) so that
    goals with extra fields, like willingness_to_pay_signals' estimated_wtp_tier or
    tool_switching_signals' from_tool/to_tool/reason, aren't stripped by schema enforcement.
    """
    properties = {}
    required = []
    for col in columns:
        field_id = col['id']
        if field_id == 'source_url':
            continue
        properties[field_id] = {"type": "string"}
        required.append(field_id)
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }

@retry(**RETRY)
def extract_info_with_gemini(text_content, prompt, response_schema):
    """Uses Gemini with schema-enforced JSON output to extract structured information from text, retrying on transient API errors."""
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
    )
    response = model.generate_content(
        prompt + "\n\nHere is the text:\n---\n" + text_content,
        generation_config=generation_config,
    )
    return response.text.strip()

def parse_multiple_json(json_string):
    """
    Fallback parser: walks a string decoding one JSON value at a time via
    JSONDecoder.raw_decode, tolerating concatenated objects and stray text
    between them. Top-level arrays are flattened into individual objects.
    """
    decoder = json.JSONDecoder()
    results = []
    idx = 0
    length = len(json_string)
    while idx < length:
        while idx < length and json_string[idx] in ' \t\n\r':
            idx += 1
        if idx >= length:
            break
        try:
            obj, end_idx = decoder.raw_decode(json_string, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, list):
            results.extend(obj)
        else:
            results.append(obj)
        idx = end_idx
    return results

@retry(**RETRY)
def generate_embedding(text):
    """Generates a text-embedding-004 embedding vector for text, retrying on transient API errors."""
    if not text:
        return []
    result = genai.embed_content(model=EMBEDDING_MODEL, content=text)
    return result['embedding']

def _cosine_similarity(a, b):
    """Computes cosine similarity between two equal-length numeric vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def find_similar_insights(insight_id, top_k=10):
    """
    Finds the top_k insights most similar to insight_id (by cosine similarity
    of their embeddings) within the same analysis_goal.

    TODO: this computes similarity over every insight for the goal in Python,
    which is fine for the first few thousand insights but won't scale —
    Firestore has no native vector search on the free tier. Move to Supabase
    pgvector once volume exceeds ~10k insights.
    """
    db = firestore.Client()
    target_doc = db.collection('insights').document(insight_id).get()
    if not target_doc.exists:
        raise ValueError(f"insight {insight_id} not found")

    target = target_doc.to_dict()
    target_embedding = target.get('embedding')
    if not target_embedding:
        return []

    candidates = db.collection('insights').where('analysis_goal', '==', target.get('analysis_goal')).stream()

    scored = []
    for doc in candidates:
        if doc.id == insight_id:
            continue
        data = doc.to_dict()
        embedding = data.get('embedding')
        if not embedding:
            continue
        scored.append((_cosine_similarity(target_embedding, embedding), doc.id, data))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [{'id': doc_id, 'similarity': score, **data} for score, doc_id, data in scored[:top_k]]

PROMPT_LIBRARY = {
    'pain_points': {
        "version": 1,
        "prompt": '''You are a market research analyst. Your goal is to identify user-expressed problems, frustrations, or unmet needs in the provided text. Scan the entire text for any indication of a complaint, wish, or struggle, even if not explicitly stated. For each pain point you find, extract the following into a JSON object: 1. "insight": A concise summary of the user's pain point. 2. "category": Classify the pain point (e.g., "Usability", "Pricing", "Customer Support", "Functionality"). 3. "quote": The full, direct sentence or phrase where the pain was mentioned. Return a list of JSON objects. If no pain points are found, return an empty list.''',
        "columns": [{'name': 'Pain Point', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'feature_requests': {
        "version": 1,
        "prompt": '''You are a product manager. Your goal is to identify specific feature requests or suggestions for improvement. Look for any language that suggests a desire for new functionality or changes to existing features. This could be direct ("I wish it had...") or indirect ("It would be great if..."). For each feature request you find, extract the following into a JSON object: 1. "insight": A summary of the requested feature. 2. "category": Classify the request (e.g., "New Feature", "Enhancement", "Integration", "UI/UX"). 3. "quote": The full, direct sentence where the request was made. Return a list of JSON objects. If none are found, return an empty list.''',
        "columns": [{'name': 'Feature Request', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'purchase_drivers': {
        "version": 1,
        "prompt": '''You are a marketing strategist. Your goal is to understand why customers choose a product or service. Look for any statements that reveal the motivation behind a purchase decision. This can include mentions of key features, price, brand reputation, or ease of use. For each purchase driver you find, extract the following into a JSON object: 1. "insight": A summary of the reason for the purchase. 2. "category": Classify the driver (e.g., "Key Feature", "Price", "Brand Reputation", "Ease of Use", "Recommendation"). 3. "quote": The full, direct sentence where the driver was mentioned. Return a list of JSON objects. If none are found, return an empty list.''',
        "columns": [{'name': 'Purchase Driver', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'positive_feedback': {
        "version": 1,
        "prompt": '''You are a social media manager. Your goal is to find positive feedback, praise, and testimonials. Look for compliments, success stories, and expressions of satisfaction. For each piece of positive feedback, extract the following into a JSON object: 1. "insight": A summary of what the user liked. 2. "category": Classify the topic of the praise (e.g., "Customer Service", "Product Quality", "Performance", "Value"). 3. "quote": The full, direct sentence where the praise was given. Return a list of JSON objects. If none are found, return an empty list.''',
        "columns": [{'name': 'Positive Feedback', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'lead_generation': {
        "version": 1,
        "prompt": '''You are a business development analyst. Your goal is to find companies or individuals expressing a need for business growth. Scan the text for any mention of needing more customers, increasing sales, improving their marketing pipeline, or generating leads. The language might not be direct. For each potential client, extract: {"insight": "A summary of their business growth goal.", "category": "Lead Generation", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Lead Gen Opportunity', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'cac_reduction': {
        "version": 1,
        "prompt": '''You are a financial analyst. Your goal is to find companies discussing challenges with customer acquisition costs (CAC). Look for mentions of high ad spend, improving marketing ROI, or making customer acquisition more efficient. For each company, extract: {"insight": "A summary of their cost-reduction challenge.", "category": "CAC Reduction", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Cost Reduction Need', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'brand_awareness': {
        "version": 1,
        "prompt": '''You are a PR specialist. Your goal is to find companies discussing a need to increase their brand visibility or reputation. Look for goals related to getting more press, improving public perception, or general brand awareness. For each company, extract: {"insight": "A summary of their brand awareness goal.", "category": "Brand Awareness", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Brand Goal', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'market_expansion': {
        "version": 1,
        "prompt": '''You are a market expansion strategist. Your goal is to find companies planning to enter new markets, launch new product lines, or expand their business to new regions. For each company, extract: {"insight": "A summary of their expansion plan.", "category": "Market Expansion", "quote": "The direct sentence where the plan was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Expansion Plan', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'workflow_automation': {
        "version": 1,
        "prompt": '''You are an operations consultant. Your goal is to find companies discussing inefficiencies or the need to automate manual processes. Look for mentions of reducing man-hours, improving operational efficiency, or streamlining workflows. For each company, extract: {"insight": "A summary of their inefficiency pain point.", "category": "Workflow Automation", "quote": "The direct sentence where the pain point was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Automation Opportunity', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'hiring_talent': {
        "version": 1,
        "prompt": '''You are a recruiter. Your goal is to find companies that are hiring or struggling to find talent. Look for mentions of open roles, scaling teams, or challenges in talent acquisition. For each company, extract: {"insight": "A summary of their hiring or talent needs.", "category": "Talent Acquisition", "quote": "The direct sentence where the need was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Hiring Need', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'supply_chain': {
        "version": 1,
        "prompt": '''You are a logistics expert. Your goal is to find companies mentioning challenges in their supply chain. Look for discussions about improving logistics, reducing shipping times, or bottlenecks. For each company, extract: {"insight": "A summary of their supply chain challenge.", "category": "Supply Chain", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Supply Chain Issue', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'customer_retention': {
        "version": 1,
        "prompt": '''You are a customer success manager. Your goal is to find companies focused on retaining customers. Look for discussions about reducing churn, improving loyalty, or increasing customer lifetime value (LTV). For each, extract: {"insight": "A summary of their retention goal.", "category": "Customer Retention", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Retention Goal', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'customer_support': {
        "version": 1,
        "prompt": '''You are a customer support analyst. Your goal is to find companies discussing challenges in their customer support operations. Look for mentions of long ticket times, improving customer satisfaction (CSAT), or scaling customer service. For each, extract: {"insight": "A summary of their support challenge.", "category": "Customer Support", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Support Challenge', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'user_feedback': {
        "version": 1,
        "prompt": '''You are a product researcher. Your goal is to find companies actively seeking feedback on their products or services. Look for requests for user feedback, beta testers, or product reviews. For each, extract: {"insight": "A summary of what they are seeking feedback on.", "category": "User Feedback", "quote": "The direct sentence where feedback was requested."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Feedback Request', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'executive_subtext': {
        "version": 1,
        "prompt": '''You are an expert organizational psychologist and business analyst. Your goal is to detect hidden meanings, stress, or problems in seemingly positive corporate communications. Analyze text from business leaders for "positive" statements that might hide negative subtext like burnout, resource shortages, or strategic struggles. For example, "the team really grinded it out" could suggest burnout. For each potential subtext, extract: 1. "insight": What is the potential hidden negative meaning? 2. "category": Classify the issue (e.g., "Team Burnout", "Strategic Uncertainty", "Resource Strain"). 3. "quote": The full, seemingly positive sentence that contains the subtext. Return a list of JSON objects.''',
        "columns": [{'name': 'Potential Subtext', 'id': 'insight'}, {'name': 'Inferred Issue', 'id': 'category'}, {'name': 'Original Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'willingness_to_pay_signals': {
        "version": 1,
        "prompt": """You are a market analyst hunting for revenue signals. Scan the text for any indication a person or business would spend money to solve a problem. Look for phrases like: "I would pay", "someone should build", "I'd give money for", "why doesn't X exist", "I've been looking for", "willing to pay $X for", "shut up and take my money". For each signal, extract: 1. "insight": what they would pay for. 2. "category": problem area (e.g., "Scheduling", "Inventory", "Reporting", "Compliance"). 3. "quote": the direct sentence. 4. "estimated_wtp_tier": "unknown" | "low_under_50" | "mid_50_to_500" | "high_500_plus" based on context. Return a list of JSON objects.""",
        "columns": [{'name': 'Would Pay For', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'WTP Tier', 'id': 'estimated_wtp_tier'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'tool_switching_signals': {
        "version": 1,
        "prompt": """You are a competitive intelligence analyst. Find any mention of switching between tools, abandoning a tool, or seeking alternatives. Look for phrases like: "we switched from X to Y because", "X is killing us", "looking for alternative to X", "X used to be good but", "moving off of X", "X is the worst". For each signal, extract: 1. "insight": summary of the switch or search. 2. "category": always "Tool Switching". 3. "quote": the direct sentence. 4. "from_tool": the tool being left (or null). 5. "to_tool": the tool being adopted (or null). 6. "reason": the stated reason for the switch. Return a list of JSON objects.""",
        "columns": [{'name': 'Switching Signal', 'id': 'insight'}, {'name': 'From Tool', 'id': 'from_tool'}, {'name': 'To Tool', 'id': 'to_tool'}, {'name': 'Reason', 'id': 'reason'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    }
}

def parse_targets(sites_str):
    """
    Parses sites_str (one target per line, or comma-separated plain URLs on a
    line) into (source_type, source_config) tuples:
      https://example.com/post              -> ('web', {'url': ...})
      reddit:<subreddit>:<kw1,kw2>           -> ('reddit', {'subreddit': ..., 'keywords': [...]})
      x:<kw1,kw2>                            -> ('x', {'keywords': [...]})
      hn:<kw1,kw2>                           -> ('hackernews', {'keywords': [...]})
      stackoverflow:<kw1,kw2>                -> ('stackexchange', {'site': 'stackoverflow', 'keywords': [...]})
      stackexchange:<site>:<kw1,kw2>         -> ('stackexchange', {'site': ..., 'keywords': [...]})
    Anything else becomes ('invalid', {'raw': ...}) so the caller can log and skip it.
    """
    targets = []
    prefixes = ('reddit:', 'x:', 'hn:', 'stackoverflow:', 'stackexchange:')
    for line in sites_str.split('\n'):
        line = line.strip()
        if not line:
            continue
        # These entries carry commas between keywords, so only split
        # plain lines on commas to support multiple URLs per line.
        if line.startswith(prefixes):
            entries = [line]
        else:
            entries = [e.strip() for e in line.split(',') if e.strip()]

        for entry in entries:
            if entry.startswith('reddit:'):
                parts = entry.split(':', 2)
                if len(parts) != 3 or not parts[1].strip() or not parts[2].strip():
                    targets.append(('invalid', {'raw': entry}))
                    continue
                _, subreddit, keywords_str = parts
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                targets.append(('reddit', {'subreddit': subreddit.strip(), 'keywords': keywords}))
            elif entry.startswith('x:'):
                _, _, keywords_str = entry.partition(':')
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                if not keywords:
                    targets.append(('invalid', {'raw': entry}))
                    continue
                targets.append(('x', {'keywords': keywords}))
            elif entry.startswith('hn:'):
                _, _, keywords_str = entry.partition(':')
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                if not keywords:
                    targets.append(('invalid', {'raw': entry}))
                    continue
                targets.append(('hackernews', {'keywords': keywords}))
            elif entry.startswith('stackoverflow:'):
                _, _, keywords_str = entry.partition(':')
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                if not keywords:
                    targets.append(('invalid', {'raw': entry}))
                    continue
                targets.append(('stackexchange', {'site': 'stackoverflow', 'keywords': keywords}))
            elif entry.startswith('stackexchange:'):
                parts = entry.split(':', 2)
                if len(parts) != 3 or not parts[1].strip() or not parts[2].strip():
                    targets.append(('invalid', {'raw': entry}))
                    continue
                _, site, keywords_str = parts
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                targets.append(('stackexchange', {'site': site.strip(), 'keywords': keywords}))
            elif entry.startswith(('http://', 'https://')):
                targets.append(('web', {'url': entry}))
            else:
                targets.append(('invalid', {'raw': entry}))
    return targets

def _describe_target(source_type, source_config):
    """Formats a human-readable label for a dispatch target, used in log messages."""
    if source_type == 'web':
        return source_config['url']
    if source_type == 'reddit':
        return f"r/{source_config['subreddit']} for {source_config['keywords']}"
    if source_type == 'x':
        return f"X search for {source_config['keywords']}"
    if source_type == 'hackernews':
        return f"HN search for {source_config['keywords']}"
    if source_type == 'stackexchange':
        return f"{source_config['site']} search for {source_config['keywords']}"
    return str(source_config)

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

def analyze_raw_content(raw_content_id, analysis_goal):
    """
    Reads a raw_content doc, extracts insights with Gemini using analysis_goal's
    prompt, embeds each insight, and upserts it via upsert_insight (semantic
    merge by embedding similarity, with mention-level dedup so reprocessing
    doesn't inflate mention_count). Returns the list of insight doc IDs touched.
    """
    db = firestore.Client()
    raw_doc = db.collection('raw_content').document(raw_content_id).get()
    if not raw_doc.exists:
        raise ValueError(f"raw_content document {raw_content_id} not found")
    raw = raw_doc.to_dict()

    goal_details = PROMPT_LIBRARY.get(analysis_goal)
    if not goal_details:
        raise ValueError(f"Invalid analysis goal '{analysis_goal}'")

    prompt_version = goal_details.get('version', 1)
    response_schema = _build_response_schema(goal_details['columns'])
    extracted_info_json = extract_info_with_gemini(raw['text'], goal_details['prompt'], response_schema)

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
        candidates = db.collection('insights').where('analysis_goal', '==', analysis_goal).stream()

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
        # Client-side, not firestore.SERVER_TIMESTAMP: the sentinel raises
        # TypeError inside an array element (this dict lands in mentions[]
        # via ArrayUnion below), confirmed against the emulator.
        'seen_at': datetime.datetime.now(datetime.timezone.utc),
    }

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
            transaction.update(doc_ref, {
                'mentions': updated_mentions,
                'last_seen': firestore.SERVER_TIMESTAMP,
            })
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
        # Client-side, not firestore.SERVER_TIMESTAMP -- see the matching
        # comment in _merge_into_existing_insight's new_mention.
        'seen_at': datetime.datetime.now(datetime.timezone.utc),
    }]
    doc['first_seen'] = firestore.SERVER_TIMESTAMP
    doc['last_seen'] = firestore.SERVER_TIMESTAMP
    doc['timestamp'] = firestore.SERVER_TIMESTAMP  # kept for backward compat with existing queries

    db.collection('insights').document(content_hash).set(doc, merge=True)
    return content_hash


TREND_WINDOW_DAYS = 7


def compute_trends(db=None):
    """
    Computes 7-day mention velocity per analysis_goal, based on
    mentions[].seen_at timestamps on each insight doc.

    current window:  seen_at in [now - 7d, now)
    previous window: seen_at in [now - 14d, now - 7d)
    score = current_count - previous_count (delta, avoids div-by-zero)

    label:
      previous_count == 0 and current_count > 0 -> "new"
      score > 0                                  -> "rising"
      score < 0                                  -> "falling"
      score == 0                                 -> "flat"

    Mentions missing `seen_at` (pre-migration data) are excluded from both
    windows rather than backfilled -- acceptable at current data volume,
    revisit if historical accuracy matters later.

    Writes one doc per insight per run to `trend_history`:
      { insight_id, analysis_goal, computed_at, window_start, window_end,
        current_count, previous_count, score, label }

    Also writes `trend` and `trend_score` back onto the insight doc itself
    for dashboard consumption (latest value only, no history there).
    """
    if db is None:
        db = firestore.Client()

    now = datetime.datetime.now(datetime.timezone.utc)
    window_start_current = now - datetime.timedelta(days=TREND_WINDOW_DAYS)
    window_start_previous = now - datetime.timedelta(days=TREND_WINDOW_DAYS * 2)

    insights = db.collection('insights').stream()
    results = []

    for doc in insights:
        data = doc.to_dict()
        mentions = data.get('mentions', [])

        current_count = 0
        previous_count = 0

        for m in mentions:
            seen_at = m.get('seen_at')
            if seen_at is None:
                continue  # pre-migration mention, excluded from windowing
            if window_start_current <= seen_at < now:
                current_count += 1
            elif window_start_previous <= seen_at < window_start_current:
                previous_count += 1

        score = current_count - previous_count

        if previous_count == 0 and current_count > 0:
            label = "new"
        elif score > 0:
            label = "rising"
        elif score < 0:
            label = "falling"
        else:
            label = "flat"

        trend_record = {
            'insight_id': doc.id,
            'analysis_goal': data.get('analysis_goal'),
            'computed_at': firestore.SERVER_TIMESTAMP,
            'window_start': window_start_current,
            'window_end': now,
            'current_count': current_count,
            'previous_count': previous_count,
            'score': score,
            'label': label,
        }

        db.collection('trend_history').document().set(trend_record)

        db.collection('insights').document(doc.id).update({
            'trend': label,
            'trend_score': score,
        })

        results.append(trend_record)

    return results


def run_scraper_analysis(api_key, analysis_goal, sites_str):
    log_messages = []
    # This helper function can be simplified now that we don't use background callbacks
    def log(message):
        print(message)
        log_messages.append(message)

    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        log(f"Error configuring Gemini API: {e}")
        return None, None, log_messages

    goal_details = PROMPT_LIBRARY.get(analysis_goal)
    if not goal_details:
        log(f"Error: Invalid analysis goal '{analysis_goal}'")
        return None, None, log_messages

    columns = goal_details["columns"]
    all_results = []

    # Handle the #google command
    lines = sites_str.split('\n')
    targets = []

    if lines and lines[0].strip().startswith("#google"):
        google_search_query = lines[0].strip()[7:].strip()
        if not google_search_query:
            log("Error: #google command used without a search query.")
            return "error", None, ["Error: #google command used without a search query."]

        log(f"Using Google Search with query: {google_search_query}")
        try:
            # You need to have discover_urls_with_google available or imported
            from backend import discover_urls_with_google
            discovered_urls = discover_urls_with_google(google_search_query)
            if not discovered_urls:
                log("Google search returned no URLs.")
            targets = [('web', {'url': u}) for u in discovered_urls]
        except Exception as e:
            log(f"An error occurred during Google search: {e}")
            return "error", None, log_messages
    else:
        targets = parse_targets(sites_str)

    for source_type, source_config in targets:
        source_cls = SOURCES.get(source_type)
        if not source_cls:
            log(f"Skipping invalid target: {source_config.get('raw', source_type)}")
            continue

        label = _describe_target(source_type, source_config)
        log(f"--- Processing: {label} ---")
        try:
            raw_items = source_cls().fetch(source_config)
        except Exception as e:
            log(f"Error fetching {label}: {e}")
            continue

        if not raw_items:
            log(f"Failed to fetch content from {label}. Skipping.")
            continue

        for raw_item in raw_items:
            try:
                raw_content_id = write_raw_content(
                    raw_item['source_type'], raw_item['source_url'], raw_item['text'],
                    subreddit=raw_item.get('subreddit')
                )
            except Exception as e:
                log(f"Error writing raw_content for {raw_item['source_url']}: {e}")
                continue

            log(f"Text fetched. Analyzing with goal: {analysis_goal}...")
            try:
                insights = analyze_raw_content(raw_content_id, analysis_goal)
            except Exception as e:
                log(f"Analysis failed for {raw_item['source_url']}: {e}")
                continue

            log(f"Analysis complete for {raw_item['source_url']}. {len(insights)} insight(s) saved.")
            all_results.extend(insights)

    if all_results:
        log(f"--- Success! {len(all_results)} insights saved to Firestore ---")
        return "success", columns, log_messages

    log("Analysis complete, but no new insights were found.")
    return "no_results", columns, log_messages
