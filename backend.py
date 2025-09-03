# backend.py

import os
import requests
import json
import datetime
import io
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from googleapiclient.discovery import build
from wordcloud import WordCloud
import pandas as pd
from dotenv import load_dotenv
from flask_cors import cross_origin


# It's best to move all logic functions into scraper_logic.py,
# but for simplicity in this step, we'll keep them here.
# We'll import the main analysis function.
from scraper_logic import run_scraper_analysis, PROMPT_LIBRARY

# --- Initialize Flask App ---
load_dotenv()
app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing

# --- Helper Functions (from your various files) ---

def discover_urls_with_google(query, num_results=10):
    """Uses the Google Custom Search API to find URLs for a given query."""
    API_KEY = os.environ.get("GOOGLE_API_KEY")
    SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")
    if not API_KEY or not SEARCH_ENGINE_ID:
        raise ValueError("GOOGLE_API_KEY and SEARCH_ENGINE_ID must be set.")
    try:
        service = build("customsearch", "v1", developerKey=API_KEY)
        result = service.cse().list(
            q=query, cx=SEARCH_ENGINE_ID, num=num_results, dateRestrict="d7"
        ).execute()
        return [item['link'] for item in result.get('items', [])]
    except Exception as e:
        print(f"An error occurred with the Google Search API: {e}")
        return []

# --- API Endpoints ---

@app.route('/api/discover', methods=['POST'])
def discover_endpoint():
    """Endpoint to discover new URLs based on a search query."""
    data = request.get_json()
    query = data.get('query')
    if not query:
        return jsonify({"error": "A 'query' parameter is required."}), 400
    
    try:
        urls = discover_urls_with_google(query)
        return jsonify({"urls": urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_endpoint():
    """Endpoint to run the main scraper analysis."""
    data = request.get_json()
    api_key = data.get('apiKey')
    analysis_goal = data.get('analysisGoal')
    sites = data.get('sites')

    if not all([api_key, analysis_goal, sites]):
        return jsonify({"error": "Missing required fields: apiKey, analysisGoal, sites"}), 400
    
    start_time = datetime.datetime.now(datetime.timezone.utc)
    
    # This function now needs to be slightly adapted to not return Dash components
    # but instead return a status and the log messages.
    result_message, columns, log_messages = run_scraper_analysis(api_key, analysis_goal, sites)

    if result_message not in ["success", "no_results"]:
         return jsonify({"error": "Analysis failed.", "logs": log_messages}), 500

    # Fetch results from Firestore that were just added
    try:
        db = firestore.Client()
        query = db.collection('insights').where(filter=firestore.FieldFilter('timestamp', '>=', start_time))
        docs = [doc.to_dict() for doc in query.stream()]

        if not docs:
            return jsonify({"message": "Analysis complete, but no new insights were found.", "data": [], "columns": columns})

        # Process data for JSON response
        df = pd.DataFrame(docs)
        if 'timestamp' in df.columns:
            df['timestamp'] = df['timestamp'].astype(str) # Convert timestamp for JSON
        
        table_data = df.to_dict('records')
        
        # Generate word cloud
        insight_text = ' '.join(df['insight'].dropna())
        wordcloud_src = ""
        if insight_text.strip():
            wordcloud = WordCloud(width=400, height=300, background_color='white', colormap='viridis').generate(insight_text)
            img_buffer = io.BytesIO()
            wordcloud.to_image().save(img_buffer, format='PNG')
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            wordcloud_src = f'data:image/png;base64,{img_base64}'

        return jsonify({
            "message": "Analysis successful!",
            "data": table_data,
            "columns": columns,
            "wordcloud": wordcloud_src
        })

    except Exception as e:
        return jsonify({"error": f"Error reading from Firestore: {e}"}), 500


@app.route('/api/search', methods=['POST'])
def search_endpoint():
    """Endpoint to perform a global search using Algolia."""
    data = request.get_json()
    search_term = data.get('searchTerm')
    if not search_term:
        return jsonify({"error": "A 'searchTerm' is required."}), 400

    ALGOLIA_APP_ID = os.environ.get("ALGOLIA_APP_ID")
    ALGOLIA_SEARCH_KEY = os.environ.get("ALGOLIA_SEARCH_ONLY_API_KEY")
    ALGOLIA_INDEX_NAME = "vectr_insights"
    
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": ALGOLIA_SEARCH_KEY,
    }
    url = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/query"
    payload = {"params": f"query={search_term}"}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        results = response.json().get('hits', [])
        return jsonify({"data": results})
    except Exception as e:
        return jsonify({"error": f"An error occurred during search: {e}"}), 500
    
@app.route('/api/insights', methods=['GET'])
@cross_origin()
def get_insights():
    """Fetches all insights from the Firestore database."""
    try:
        db = firestore.Client()
        insights_ref = db.collection('insights')
        docs = insights_ref.stream()

        insights_list = []
        for doc in docs:
            insight_data = doc.to_dict()
            insight_data['id'] = doc.id
            insights_list.append(insight_data)

        return jsonify(insights_list)

    except Exception as e:
        print(f"Error fetching insights: {e}")
        return jsonify({'error': 'Failed to fetch insights'}), 500

# To run this backend server locally:
if __name__ == '__main__':
    # Use port 5001 to avoid conflict with default React port (3000) or Flask default (5000)
    app.run(debug=True, port=5001)
