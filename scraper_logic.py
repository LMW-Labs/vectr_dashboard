# scraper_logic.py
import os
import hashlib
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import time
from google.cloud import firestore
import tweepy
import praw
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_exponential

# Import the new secret manager helper
from secret_manager import get_secret

_RETRY = dict(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)

@retry(**_RETRY)
def scrape_website_text(url):
    """Fetches and extracts clean text from a given URL, retrying transient request failures."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    for script_or_style in soup(['script', 'style']):
        script_or_style.decompose()
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = '\n'.join(chunk for chunk in chunks if chunk)
    return clean_text

def _build_response_schema(columns):
    """Builds a Gemini JSON response schema (array of objects) from a PROMPT_LIBRARY columns list."""
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

@retry(**_RETRY)
def extract_info_with_gemini(text_content, prompt, response_schema=None):
    """Uses Gemini to extract structured information from text, enforcing a JSON schema when provided."""
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    generation_config = None
    if response_schema is not None:
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
        )
    response = model.generate_content(
        prompt + "\n\nHere is the text:\n---\n" + text_content,
        generation_config=generation_config,
    )
    cleaned_response = response.text.strip().replace('```json', '').replace('```', '')
    return cleaned_response

def parse_multiple_json(json_string):
    """
    Parses a string that may contain one or more JSON objects/arrays (single object,
    array of objects, concatenated objects, or nested dicts/lists) into a flat list of dicts.
    """
    if not json_string:
        return []

    decoder = json.JSONDecoder()
    results = []
    idx = 0
    length = len(json_string)

    while idx < length:
        while idx < length and json_string[idx] not in '{[':
            idx += 1
        if idx >= length:
            break
        try:
            obj, end_idx = decoder.raw_decode(json_string, idx)
        except json.JSONDecodeError:
            idx += 1
            continue

        if isinstance(obj, list):
            results.extend(item for item in obj if isinstance(item, dict))
        elif isinstance(obj, dict):
            results.append(obj)

        idx = end_idx

    return results

@retry(**_RETRY)
def fetch_from_x_api(keywords):
    """
    Searches for recent tweets using the X API v2 and returns their text.
    """
    bearer_token = get_secret("X_BEARER_TOKEN")

    if not bearer_token:
        print("Error: X_BEARER_TOKEN not found in Secret Manager.")
        return None

    client = tweepy.Client(bearer_token)
    query = f"({' OR '.join(keywords)}) -is:retweet lang:en"
    response = client.search_recent_tweets(query=query, max_results=100)

    tweets = response.data
    if not tweets:
        print("No tweets found for the given keywords.")
        return ""

    combined_text = "\n".join(tweet.text for tweet in tweets)
    return combined_text

@retry(**_RETRY)
def fetch_from_reddit_api(subreddit, keywords):
    """
    Searches a subreddit for keywords and returns the content of new posts.
    """
    reddit = praw.Reddit(
        client_id=get_secret("REDDIT_CLIENT_ID"),
        client_secret=get_secret("REDDIT_CLIENT_SECRET"),
        user_agent=get_secret("REDDIT_USER_AGENT"),
    )

    query = ' OR '.join(f'"{keyword}"' for keyword in keywords)
    combined_text = ""
    for submission in reddit.subreddit(subreddit).search(query, sort='new', time_filter='week'):
        combined_text += submission.title + "\n" + submission.selftext + "\n\n"

    if not combined_text:
        print(f"No new posts found in r/{subreddit} for the given keywords.")

    return combined_text

def parse_targets(sites_str, log=None):
    """Parses sites_str (one target per line, URLs may also be comma-separated) into (source_type, config) tuples."""
    targets = []
    if not sites_str:
        return targets

    def _log(message):
        if log:
            log(message)

    for raw_line in sites_str.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        lowered = line.lower()
        if lowered.startswith('reddit:'):
            parts = line.split(':', 2)
            if len(parts) != 3 or not parts[1].strip() or not parts[2].strip():
                _log(f"Skipping malformed reddit target: {line}")
                continue
            subreddit = parts[1].strip()
            keywords = [k.strip() for k in parts[2].split(',') if k.strip()]
            if not keywords:
                _log(f"Skipping malformed reddit target: {line}")
                continue
            targets.append(('reddit', {'subreddit': subreddit, 'keywords': keywords}))
        elif lowered.startswith('x:'):
            _, _, keywords_str = line.partition(':')
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            if not keywords:
                _log(f"Skipping malformed x target: {line}")
                continue
            targets.append(('x', {'keywords': keywords}))
        else:
            for chunk in line.split(','):
                url = chunk.strip()
                if not url:
                    continue
                if not url.startswith(('http://', 'https://')):
                    _log(f"Skipping invalid URL: {url}")
                    continue
                targets.append(('web', {'url': url}))

    return targets

PROMPT_LIBRARY = {
    'pain_points': {
        "prompt": '''You are a market research analyst. Your goal is to identify user-expressed problems, frustrations, or unmet needs in the provided text. Scan the entire text for any indication of a complaint, wish, or struggle, even if not explicitly stated. For each pain point you find, extract the following into a JSON object: 1. "insight": A concise summary of the user's pain point. 2. "category": Classify the pain point (e.g., "Usability", "Pricing", "Customer Support", "Functionality"). 3. "quote": The full, direct sentence or phrase where the pain was mentioned. Return a list of JSON objects. If no pain points are found, return an empty list.''',
        "columns": [{'name': 'Pain Point', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'feature_requests': {
        "prompt": '''You are a product manager. Your goal is to identify specific feature requests or suggestions for improvement. Look for any language that suggests a desire for new functionality or changes to existing features. This could be direct ("I wish it had...") or indirect ("It would be great if..."). For each feature request you find, extract the following into a JSON object: 1. "insight": A summary of the requested feature. 2. "category": Classify the request (e.g., "New Feature", "Enhancement", "Integration", "UI/UX"). 3. "quote": The full, direct sentence where the request was made. Return a list of JSON objects. If none are found, return an empty list.''',
        "columns": [{'name': 'Feature Request', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'purchase_drivers': {
        "prompt": '''You are a marketing strategist. Your goal is to understand why customers choose a product or service. Look for any statements that reveal the motivation behind a purchase decision. This can include mentions of key features, price, brand reputation, or ease of use. For each purchase driver you find, extract the following into a JSON object: 1. "insight": A summary of the reason for the purchase. 2. "category": Classify the driver (e.g., "Key Feature", "Price", "Brand Reputation", "Ease of Use", "Recommendation"). 3. "quote": The full, direct sentence where the driver was mentioned. Return a list of JSON objects. If none are found, return an empty list.''',
        "columns": [{'name': 'Purchase Driver', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'positive_feedback': {
        "prompt": '''You are a social media manager. Your goal is to find positive feedback, praise, and testimonials. Look for compliments, success stories, and expressions of satisfaction. For each piece of positive feedback, extract the following into a JSON object: 1. "insight": A summary of what the user liked. 2. "category": Classify the topic of the praise (e.g., "Customer Service", "Product Quality", "Performance", "Value"). 3. "quote": The full, direct sentence where the praise was given. Return a list of JSON objects. If none are found, return an empty list.''',
        "columns": [{'name': 'Positive Feedback', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'lead_generation': {
        "prompt": '''You are a business development analyst. Your goal is to find companies or individuals expressing a need for business growth. Scan the text for any mention of needing more customers, increasing sales, improving their marketing pipeline, or generating leads. The language might not be direct. For each potential client, extract: {"insight": "A summary of their business growth goal.", "category": "Lead Generation", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Lead Gen Opportunity', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'cac_reduction': {
        "prompt": '''You are a financial analyst. Your goal is to find companies discussing challenges with customer acquisition costs (CAC). Look for mentions of high ad spend, improving marketing ROI, or making customer acquisition more efficient. For each company, extract: {"insight": "A summary of their cost-reduction challenge.", "category": "CAC Reduction", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Cost Reduction Need', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'brand_awareness': {
        "prompt": '''You are a PR specialist. Your goal is to find companies discussing a need to increase their brand visibility or reputation. Look for goals related to getting more press, improving public perception, or general brand awareness. For each company, extract: {"insight": "A summary of their brand awareness goal.", "category": "Brand Awareness", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Brand Goal', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'market_expansion': {
        "prompt": '''You are a market expansion strategist. Your goal is to find companies planning to enter new markets, launch new product lines, or expand their business to new regions. For each company, extract: {"insight": "A summary of their expansion plan.", "category": "Market Expansion", "quote": "The direct sentence where the plan was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Expansion Plan', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'workflow_automation': {
        "prompt": '''You are an operations consultant. Your goal is to find companies discussing inefficiencies or the need to automate manual processes. Look for mentions of reducing man-hours, improving operational efficiency, or streamlining workflows. For each company, extract: {"insight": "A summary of their inefficiency pain point.", "category": "Workflow Automation", "quote": "The direct sentence where the pain point was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Automation Opportunity', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'hiring_talent': {
        "prompt": '''You are a recruiter. Your goal is to find companies that are hiring or struggling to find talent. Look for mentions of open roles, scaling teams, or challenges in talent acquisition. For each company, extract: {"insight": "A summary of their hiring or talent needs.", "category": "Talent Acquisition", "quote": "The direct sentence where the need was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Hiring Need', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'supply_chain': {
        "prompt": '''You are a logistics expert. Your goal is to find companies mentioning challenges in their supply chain. Look for discussions about improving logistics, reducing shipping times, or bottlenecks. For each company, extract: {"insight": "A summary of their supply chain challenge.", "category": "Supply Chain", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Supply Chain Issue', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'customer_retention': {
        "prompt": '''You are a customer success manager. Your goal is to find companies focused on retaining customers. Look for discussions about reducing churn, improving loyalty, or increasing customer lifetime value (LTV). For each, extract: {"insight": "A summary of their retention goal.", "category": "Customer Retention", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Retention Goal', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'customer_support': {
        "prompt": '''You are a customer support analyst. Your goal is to find companies discussing challenges in their customer support operations. Look for mentions of long ticket times, improving customer satisfaction (CSAT), or scaling customer service. For each, extract: {"insight": "A summary of their support challenge.", "category": "Customer Support", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Support Challenge', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'user_feedback': {
        "prompt": '''You are a product researcher. Your goal is to find companies actively seeking feedback on their products or services. Look for requests for user feedback, beta testers, or product reviews. For each, extract: {"insight": "A summary of what they are seeking feedback on.", "category": "User Feedback", "quote": "The direct sentence where feedback was requested."}. Return a list of JSON objects.''',
        "columns": [{'name': 'Feedback Request', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'executive_subtext': {
        "prompt": '''You are an expert organizational psychologist and business analyst. Your goal is to detect hidden meanings, stress, or problems in seemingly positive corporate communications. Analyze text from business leaders for "positive" statements that might hide negative subtext like burnout, resource shortages, or strategic struggles. For example, "the team really grinded it out" could suggest burnout. For each potential subtext, extract: 1. "insight": What is the potential hidden negative meaning? 2. "category": Classify the issue (e.g., "Team Burnout", "Strategic Uncertainty", "Resource Strain"). 3. "quote": The full, seemingly positive sentence that contains the subtext. Return a list of JSON objects.''',
        "columns": [{'name': 'Potential Subtext', 'id': 'insight'}, {'name': 'Inferred Issue', 'id': 'category'}, {'name': 'Original Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
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
}

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

    extraction_prompt = goal_details["prompt"]
    columns = goal_details["columns"]
    response_schema = _build_response_schema(columns)
    all_results = []

    # Handle the #google command
    sites = sites_str.split('\n') if sites_str else []
    working_sites_str = sites_str

    if sites and sites[0].startswith("#google"):
        google_search_query = sites[0][7:].strip()
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
            working_sites_str = '\n'.join(discovered_urls)
        except Exception as e:
            log(f"An error occurred during Google search: {e}")
            return "error", None, log_messages

    targets = parse_targets(working_sites_str, log=log)

    for source_type, config in targets:
        text_content = None
        source_url = None

        if source_type == 'web':
            source_url = config['url']
            log(f"--- Processing: {source_url} ---")
            try:
                text_content = scrape_website_text(source_url)
            except requests.exceptions.RequestException as e:
                log(f"Error fetching URL {source_url}: {e}")
                text_content = None
        elif source_type == 'reddit':
            subreddit = config['subreddit']
            keywords = config['keywords']
            source_url = f"reddit://r/{subreddit}?q={','.join(keywords)}"
            log(f"--- Processing Reddit: r/{subreddit} ({', '.join(keywords)}) ---")
            try:
                text_content = fetch_from_reddit_api(subreddit, keywords)
            except Exception as e:
                log(f"An error occurred with the Reddit API: {e}")
                text_content = None
        elif source_type == 'x':
            keywords = config['keywords']
            source_url = f"x://search?q={','.join(keywords)}"
            log(f"--- Processing X search: {', '.join(keywords)} ---")
            try:
                text_content = fetch_from_x_api(keywords)
            except Exception as e:
                log(f"An error occurred with the X API: {e}")
                text_content = None
        else:
            log(f"Unknown source type: {source_type}")
            continue

        if text_content:
            log(f"Text fetched. Analyzing with goal: {analysis_goal}...")
            try:
                extracted_info_json = extract_info_with_gemini(text_content, extraction_prompt, response_schema=response_schema)
            except Exception as e:
                log(f"An error occurred with the Gemini API: {e}")
                extracted_info_json = None

            if extracted_info_json:
                log("Analysis complete for this source.")
                try:
                    data = json.loads(extracted_info_json)
                    if not isinstance(data, list):
                        raise ValueError("Expected a JSON array")
                except (json.JSONDecodeError, ValueError) as e:
                    log(f"Schema-enforced JSON parse failed for {source_url}, falling back to parse_multiple_json: {e}")
                    data = parse_multiple_json(extracted_info_json)

                try:
                    for item in data:
                        if isinstance(item, dict):
                            item['source_url'] = source_url
                            all_results.append(item)
                except Exception as e:
                    log(f"Could not parse JSON response for {source_url}: {e}")
            else:
                log(f"Analysis failed for {source_url}. No data extracted.")
        else:
            log(f"Failed to fetch text from {source_url}. Skipping.")

    # Final block to save results to Firestore
    if all_results:
        try:
            db = firestore.Client()
            for insight in all_results:
                insight['timestamp'] = firestore.SERVER_TIMESTAMP
                content_hash = hashlib.sha256(
                    f"{insight.get('quote', '')}|{insight.get('source_url', '')}".encode()
                ).hexdigest()
                db.collection('insights').document(content_hash).set(insight, merge=True)

            log(f"--- Success! {len(all_results)} insights saved to Firestore ---")
            return "success", columns, log_messages

        except Exception as e:
            log(f"Error connecting to Firestore: {e}")
            return None, None, log_messages

    log("Analysis complete, but no new insights were found.")
    return "no_results", columns, log_messages
