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
from flask_cors import cross_origin
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition


# Import the new secret manager helper
from secret_manager import get_secret

# It's best to move all logic functions into scraper_logic.py,
# but for simplicity in this step, we'll keep them here.
# We'll import the main analysis function.
from scraper_logic import run_scraper_analysis, PROMPT_LIBRARY
from data_processing import clean_data, get_cleaned_data_as_csv

# --- Initialize Flask App ---
app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing

# --- Helper Functions (from your various files) ---

def discover_urls_with_google(query, num_results=10):
    """Uses the Google Custom Search API to find URLs for a given query."""
    API_KEY = get_secret("GOOGLE_API_KEY")
    SEARCH_ENGINE_ID = get_secret("SEARCH_ENGINE_ID")
    if not API_KEY or not SEARCH_ENGINE_ID:
        raise ValueError("GOOGLE_API_KEY and SEARCH_ENGINE_ID must be set in Secret Manager.")
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

@app.route('/api/upload_data', methods=['POST'])
def upload_data_endpoint():
    if 'files' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    files = request.files.getlist('files')

    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No selected file'}), 400

    all_cleaned_dfs = []
    errors = []

    for file in files:
        if file:
            file_content = file.read()
            cleaned_df, error = clean_data(file_content, file.filename)
            if error:
                errors.append(f"Error processing {file.filename}: {error}")
            else:
                all_cleaned_dfs.append(cleaned_df)

    if not all_cleaned_dfs:
        return jsonify({'error': '. '.join(errors)}), 400

    # Concatenate all cleaned dataframes
    combined_df = pd.concat(all_cleaned_dfs, ignore_index=True)
    
    # Optional: drop duplicates that might be created across files
    combined_df.drop_duplicates(inplace=True)

    cleaned_csv = get_cleaned_data_as_csv(combined_df)
    return jsonify({'cleaned_data': cleaned_csv})

@app.route('/api/share_email', methods=['POST'])
def share_email_endpoint():
    data = request.get_json()
    email = data.get('email')
    csv_data = data.get('csv_data')

    if not email or not csv_data:
        return jsonify({'error': 'Missing email or csv_data'}), 400

    SENDGRID_API_KEY = get_secret("SENDGRID_API_KEY")
    if not SENDGRID_API_KEY:
        return jsonify({'error': 'SENDGRID_API_KEY not found in Secret Manager.'}), 500

    message = Mail(
        from_email='[YOUR_VERIFIED_SENDER_EMAIL]', # Replace with a verified sender
        to_emails=email,
        subject='Cleaned CSV Data',
        html_content='<strong>Here is the cleaned data you requested.</strong>')

    encoded_file = base64.b64encode(csv_data.encode()).decode()
    attachedFile = Attachment(
        FileContent(encoded_file),
        FileName('cleaned_data.csv'),
        FileType('text/csv'),
        Disposition('attachment')
    )
    message.attachment = attachedFile

    try:
        sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code >= 200 and response.status_code < 300:
            return jsonify({'message': 'Email sent successfully'})
        else:
            return jsonify({'error': 'Failed to send email', 'details': response.body}), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/discover', methods=['POST'])
def discover_endpoint():
    """Endpoint to discover new URLs based on a search query."""
    data = request.get_json()
    query = data.get('query')
    if not query:
        return jsonify({"error": "A 'query' parameter is required."}), 400
    
    try:
        urls = discover_urls_with_google(query)
        
        # Save discovered URLs to Firestore
        db = firestore.Client()
        batch = db.batch()
        for url in urls:
            doc_ref = db.collection('discovered_sources').document()
            batch.set(doc_ref, {
                'url': url,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        batch.commit()
        
        return jsonify({"urls": urls})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discovered_sources', methods=['GET'])
def get_discovered_sources():
    """Fetches all discovered URLs from the Firestore database."""
    try:
        db = firestore.Client()
        sources_ref = db.collection('discovered_sources').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(50)
        docs = sources_ref.stream()

        sources_list = []
        for doc in docs:
            source_data = doc.to_dict()
            source_data['id'] = doc.id
            sources_list.append(source_data)

        return jsonify(sources_list)

    except Exception as e:
        print(f"Error fetching discovered sources: {e}")
        return jsonify({'error': 'Failed to fetch discovered sources'}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_endpoint():
    """Endpoint to run the main scraper analysis."""
    data = request.get_json()
    analysis_goal = data.get('analysisGoal')
    sites = data.get('sites')

    if not all([analysis_goal, sites]):
        return jsonify({"error": "Missing required fields: analysisGoal, sites"}), 400
    
    # Get the Gemini API key from Secret Manager
    api_key = get_secret("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY not found in Secret Manager."}), 500
    
    start_time = datetime.datetime.now(datetime.timezone.utc)
    
    # This function now needs to be slightly adapted to not return Dash components
    # but instead return a status and the log messages.
    result_message, columns, log_messages = run_scraper_analysis(api_key, analysis_goal, sites)

    if result_message not in ["success", "no_results"]:
         return jsonify({"error": "Analysis failed.", "logs": log_messages}), 500

    # Fetch results from Firestore that were just added
    try:
        # FIX: Introduce a buffer to avoid timestamp race conditions
        query_start_time = start_time - datetime.timedelta(seconds=10)

        db = firestore.Client()
        query = db.collection('insights').where(filter=firestore.FieldFilter('timestamp', '>=', query_start_time))
        
        # FIX: Also, ensure the document ID is added for the frontend
        docs = []
        for doc in query.stream():
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id
            docs.append(doc_data)

        if not docs:
            return jsonify({"message": "Analysis complete, but no new insights were found.", "data": [], "columns": columns})

        # Process data for JSON response
        df = pd.DataFrame(docs)
        if 'timestamp' in df.columns:
            # Ensure timestamp is a datetime object before formatting
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

        
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

    ALGOLIA_APP_ID = get_secret("ALGOLIA_APP_ID")
    ALGOLIA_SEARCH_KEY = get_secret("ALGOLIA_SEARCH_ONLY_API_KEY")
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