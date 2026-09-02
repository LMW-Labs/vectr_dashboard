# Vectr Dashboard

Internal data intelligence tool. It collects discussion from public sources on a schedule, runs the text through Gemini for extraction and summarization, and surfaces what comes back in a React dashboard.

Built to answer "what are people in this space actually complaining about" without reading a thousand threads by hand.

## How a scan runs

1. A scan is defined as a Firestore document: a cron expression, a set of sources, and the query terms.
2. `scheduled_scan.py` walks the `scans` collection and uses croniter to work out what is due.
3. Source adapters pull matching discussion. Each one implements the same interface from `sources/base.py`, so adding a source means adding one file.
4. `scraper_logic.py` sends the collected text to Gemini for extraction and summarization.
5. Insights are written back to Firestore. The React frontend reads them; results can be mailed out through SendGrid.

## Sources

| Adapter | Pulls from |
|---|---|
| `hackernews.py` | Hacker News search |
| `reddit.py` | Reddit via PRAW |
| `stackexchange.py` | Stack Exchange API |
| `quora.py` | Quora |
| `x.py` | X via Tweepy |
| `web.py` | Arbitrary pages via BeautifulSoup |

## Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, gunicorn |
| Data | Google Cloud Firestore |
| AI | Google Gemini |
| Secrets | Google Secret Manager |
| Frontend | React, Firebase Auth |
| Hosting | Firebase App Hosting (Cloud Run), Docker |

## Google Cloud

- **Firestore** holds scan configs, raw captures and generated insights.
- **Secret Manager** holds every API key. `secret_manager.py` reads them at runtime, so no key lives in code or in a deployed env file.
- **Firebase App Hosting** runs the gunicorn backend and the built frontend. `apphosting.yaml` declares the runtime secrets as `managedSecrets`, so the service account is granted access through IAM rather than the values being injected as plain environment variables.
- **Firebase Auth** gates the dashboard.

Outbound calls retry with `tenacity` — most of these APIs rate-limit, and a scan that dies halfway is worse than a slow one.

## Running locally

```
python -m venv .venv && .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in local values
python backend.py

npm install
npm start
```

Locally, keys come from `.env`. Deployed, they come from Secret Manager — `get_secret()` falls back to environment variables so the same code path works in both.

## Configuration

Firebase web config is read from `REACT_APP_FIREBASE_*` environment variables. Those values are client-side identifiers rather than secrets: they ship inside any web app's JS bundle. What protects the data is Firestore Security Rules and API key restrictions, not keeping the config out of sight.

## Status

Internal tool, published as a work sample. Not accepting contributions.