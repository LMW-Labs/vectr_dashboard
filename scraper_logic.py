# scraper_logic.py
import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import time
from google.cloud import firestore
import tweepy
import praw
from googleapiclient.discovery import build

# Import the new secret manager helper
from secret_manager import get_secret

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
    bearer_token = get_secret("X_BEARER_TOKEN")

    if not bearer_token:
        print("Error: X_BEARER_TOKEN not found in Secret Manager.")
        return None

    try:
        client = tweepy.Client(bearer_token)
        query = f"(' OR '.join(keywords)) -is:retweet lang:en"
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
    reddit = praw.Reddit(
        client_id=get_secret("REDDIT_CLIENT_ID"),
        client_secret=get_secret("REDDIT_CLIENT_SECRET"),
        user_agent=get_secret("REDDIT_USER_AGENT"),
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
    
    # Handle the #google command
    sites = sites_str.split('\n')
    target_urls = []
    google_search_query = None

    if sites and sites[0].startswith("#google"):
        google_search_query = sites[0][7:].strip()
        if not google_search_query:
            log("Error: #google command used without a search query.")
            return "error", None, ["Error: #google command used without a search query."]
        
        log(f"Using Google Search with query: {google_search_query}")
        try:
            # You need to have discover_urls_with_google available or imported
            from backend import discover_urls_with_google 
            target_urls = discover_urls_with_google(google_search_query)
            if not target_urls:
                log("Google search returned no URLs.")
        except Exception as e:
            log(f"An error occurred during Google search: {e}")
            return "error", None, log_messages
    else:
        target_urls = sites

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
