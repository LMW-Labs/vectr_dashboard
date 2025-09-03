# scraper_logic.py
import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import time
from google.cloud import firestore
from dotenv import load_dotenv
import tweepy
import praw
from googleapiclient.discovery import build # 1. ADDED MISSING IMPORT

def scrape_website_text(url):
    """Fetches and extracts clean text from a given URL."""
    try:
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
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    
def extract_info_with_gemini(text_content, prompt):
    """Uses Gemini to extract structured information from text."""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt + "\n\nHere is the text:\n---\n" + text_content)
        cleaned_response = response.text.strip().replace('```json', '').replace('```', '')
        return cleaned_response
    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        return None
    
def parse_multiple_json(json_string):
    """
    Parses a string that may contain multiple concatenated JSON objects.
    """
    import json
    import re
    json_objects_str = re.findall(r'\{.*?\}', json_string, re.DOTALL)
    results = []
    for obj_str in json_objects_str:
        try:
            results.append(json.loads(obj_str))
        except json.JSONDecodeError:
            print(f"Skipping malformed JSON object: {obj_str}")
            continue
    return results

def fetch_from_x_api(keywords):
    """
    Searches for recent tweets using the X API v2 and returns their text.
    """
    load_dotenv()
    bearer_token = os.environ.get("X_BEARER_TOKEN")

    if not bearer_token:
        print("Error: X_BEARER_TOKEN not found in .env file.")
        return None

    try:
        client = tweepy.Client(bearer_token)
        query = f"({' OR '.join(keywords)}) -is:retweet lang:en"
        response = client.search_recent_tweets(query=query, max_results=100)
        
        tweets = response.data
        if not tweets:
            print("No tweets found for the given keywords.")
            return ""

        combined_text = "\n".join(tweet.text for tweet in tweets)
        return combined_text

    except Exception as e:
        print(f"An error occurred with the X API: {e}")
        return None
    
def fetch_from_reddit_api(subreddit, keywords):
    """
    Searches a subreddit for keywords and returns the content of new posts.
    """
    load_dotenv()
    reddit = praw.Reddit(
    client_id=os.environ.get("REDDIT_CLIENT_ID"),
    client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
    user_agent=os.environ.get("REDDIT_USER_AGENT"),
)

    try:
        query = ' OR '.join(f'"{keyword}"' for keyword in keywords)
        combined_text = ""
        for submission in reddit.subreddit(subreddit).search(query, sort='new', time_filter='week'):
            combined_text += submission.title + "\n" + submission.selftext + "\n\n"
        
        if not combined_text:
            print(f"No new posts found in r/{subreddit} for the given keywords.")

        return combined_text
    
    except Exception as e:
        print(f"An error occurred with the Reddit API: {e}")
        return None

PROMPT_LIBRARY = {
    'pain_points': {
        "prompt": """You are a market research analyst. Your goal is to identify any user-expressed problem, frustration, or unmet need in the provided text. Scan the entire text for complaints, wishes, or struggles. For each pain point you find, extract the following into a JSON object: 1. "insight": A concise summary of the user's pain point. 2. "category": Classify the pain point (e.g., "Usability", "Pricing", "Customer Support"). 3. "quote": The full, direct sentence where the pain was mentioned. Return a list of JSON objects. If none are found, return an empty list.""",
        "columns": [{'name': 'Pain Point', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'feature_requests': {
        "prompt": """You are a product manager. Your goal is to identify specific feature requests or suggestions for improvement in the provided text. Look for phrases like "I wish it had", "it should do", "add a feature", or "it would be better if". For each feature request you find, extract the following into a JSON object: 1. "insight": A summary of the requested feature. 2. "category": Classify the request (e.g., "New Feature", "Enhancement", "Integration"). 3. "quote": The full, direct sentence where the request was made. Return a list of JSON objects. If none are found, return an empty list.""",
        "columns": [{'name': 'Feature Request', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'purchase_drivers': {
        "prompt": """You are a marketing strategist. Your goal is to understand why customers choose to buy a product or service, based on the provided text. Look for phrases like "the reason I bought", "sold me on", "the best feature is", or "I chose it because". For each purchase driver you find, extract the following into a JSON object: 1. "insight": A summary of the reason the customer made the purchase. 2. "category": Classify the driver (e.g., "Key Feature", "Price", "Brand Reputation", "Ease of Use"). 3. "quote": The full, direct sentence where the driver was mentioned. Return a list of JSON objects. If none are found, return an empty list.""",
        "columns": [{'name': 'Purchase Driver', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'positive_feedback': {
        "prompt": """You are a social media manager. Your goal is to find positive feedback, praise, and testimonials in the provided text. Look for compliments, success stories, and expressions of satisfaction. For each piece of positive feedback you find, extract the following into a JSON object: 1. "insight": A summary of what the user liked or their success story. 2. "category": Classify the topic of the praise (e.g., "Customer Service", "Product Quality", "Performance"). 3. "quote": The full, direct sentence where the praise was given. Return a list of JSON objects. If none are found, return an empty list.""",
        "columns": [{'name': 'Positive Feedback', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'lead_generation': {
        "prompt": """You are a business development analyst. Your goal is to find companies discussing a need to "increase leads," "improve lead quality," or "fill the sales pipeline." For each potential client you find, extract: {"insight": "A summary of their lead generation goal.", "category": "Lead Generation", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Lead Gen Opportunity', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'cac_reduction': {
        "prompt": """You are a financial analyst. Your goal is to find companies discussing "high Customer Acquisition Cost (CAC)," "reducing ad spend," or "improving marketing ROI." For each company, extract: {"insight": "A summary of their cost-reduction challenge.", "category": "CAC Reduction", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Cost Reduction Need', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'brand_awareness': {
        "prompt": """You are a PR specialist. Your goal is to find companies discussing a need to "increase brand visibility," "get more press," or "improve brand reputation." For each company, extract: {"insight": "A summary of their brand awareness goal.", "category": "Brand Awareness", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Brand Goal', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'market_expansion': {
        "prompt": """You are a market expansion strategist. Your goal is to find companies discussing "entering a new market," "expanding to a region," or "launching a new product line." For each company, extract: {"insight": "A summary of their expansion plan.", "category": "Market Expansion", "quote": "The direct sentence where the plan was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Expansion Plan', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'workflow_automation': {
        "prompt": """You are an operations consultant. Your goal is to find companies discussing "automating manual processes," "reducing man-hours," or "improving operational efficiency." For each company, extract: {"insight": "A summary of their inefficiency pain point.", "category": "Workflow Automation", "quote": "The direct sentence where the pain point was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Automation Opportunity', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'hiring_talent': {
        "prompt": """You are a recruiter. Your goal is to find companies that are "hiring for specific roles," "scaling our team," or "struggling to find talent." For each company, extract: {"insight": "A summary of their hiring or talent needs.", "category": "Talent Acquisition", "quote": "The direct sentence where the need was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Hiring Need', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'supply_chain': {
        "prompt": """You are a logistics expert. Your goal is to find companies mentioning "improving logistics," "reducing shipping times," or "supply chain bottlenecks." For each company, extract: {"insight": "A summary of their supply chain challenge.", "category": "Supply Chain", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Supply Chain Issue', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'customer_retention': {
        "prompt": """You are a customer success manager. Your goal is to find companies focused on "reducing customer churn," "improving customer loyalty," or "increasing customer lifetime value (LTV)." For each, extract: {"insight": "A summary of their retention goal.", "category": "Customer Retention", "quote": "The direct sentence where the goal was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Retention Goal', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'customer_support': {
        "prompt": """You are a customer support analyst. Your goal is to find companies discussing "long support ticket times," "improving customer satisfaction (CSAT)," or "scaling customer service." For each, extract: {"insight": "A summary of their support challenge.", "category": "Customer Support", "quote": "The direct sentence where the challenge was mentioned."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Support Challenge', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'user_feedback': {
        "prompt": """You are a product researcher. Your goal is to find companies actively seeking "user feedback," "beta testers," or "product reviews." For each, extract: {"insight": "A summary of what they are seeking feedback on.", "category": "User Feedback", "quote": "The direct sentence where feedback was requested."}. Return a list of JSON objects.""",
        "columns": [{'name': 'Feedback Request', 'id': 'insight'}, {'name': 'Category', 'id': 'category'}, {'name': 'Direct Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
    },
    'executive_subtext': {
        "prompt": """You are an expert organizational psychologist and business analyst. Your goal is to detect hidden meanings, stress, or problems in seemingly positive corporate communications. Analyze the provided text from a business leader. Look for "positive" statements that might hide negative subtext, such as burnout, resource shortages, or operational struggles. For example, a phrase like "the team really grinded it out last quarter" could be a sign of potential burnout. "Pivoting quickly" could mean a lack of clear strategy. For each potential subtext you find, extract the following into a JSON object: 1. "insight": What is the potential hidden negative meaning or "veiled cry for help"? 2. "category": Classify the issue (e.g., "Team Burnout", "Strategic Uncertainty", "Resource Strain"). 3. "quote": The full, seemingly positive sentence that contains the subtext. Return a list of JSON objects. If none are found, return an empty list.""",
        "columns": [{'name': 'Potential Subtext', 'id': 'insight'}, {'name': 'Inferred Issue', 'id': 'category'}, {'name': 'Original Quote', 'id': 'quote'}, {'name': 'Source URL', 'id': 'source_url'}]
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
    all_results = []
    target_urls = []

        # This loop will now run for standard URLs or for URLs found by the #google command
    for url in target_urls:
        if not url.startswith(('http://', 'https://')):
            log(f"Skipping invalid URL: {url}")
            continue

        log(f"--- Processing: {url} ---")
        article_text = scrape_website_text(url)
        if article_text:
            log(f"Text scraped. Analyzing with goal: {analysis_goal}...")
            extracted_info_json = extract_info_with_gemini(article_text, extraction_prompt)
            
            if extracted_info_json:
                log("Analysis complete for this URL.")
                try:
                    data = parse_multiple_json(extracted_info_json)
                    if isinstance(data, list):
                        for item in data:
                            item['source_url'] = url
                        all_results.extend(data)
                    elif isinstance(data, dict):
                        data['source_url'] = url
                        all_results.append(data)
                except Exception as e:
                    log(f"Could not parse JSON response for {url}: {e}")
            else:
                log(f"Analysis failed for {url}. No data extracted.")
        else:
            log(f"Failed to scrape text from {url}. Skipping.")

    # Final block to save results to Firestore
    if all_results:
        try:
            db = firestore.Client()
            for insight in all_results:
                insight['timestamp'] = firestore.SERVER_TIMESTAMP
                db.collection('insights').add(insight)
            
            log(f"--- Success! {len(all_results)} insights saved to Firestore ---")
            return "success", columns, log_messages
        
        except Exception as e:
            log(f"Error connecting to Firestore: {e}")
            return None, None, log_messages
    
    log("Analysis complete, but no new insights were found.")
    return "no_results", columns, log_messages