"""Runs any due scheduled scans stored in the Firestore 'scans' collection."""
import datetime
import logging

from croniter import croniter
from google.cloud import firestore

from scraper_logic import run_scraper_analysis
from secret_manager import get_secret

logger = logging.getLogger(__name__)


def _is_due(scan, now):
    """Returns True if scan's cron schedule has a fire time between last_run_at (or now) and now."""
    schedule_cron = scan.get('schedule_cron')
    if not schedule_cron:
        return False
    last_run_at = scan.get('last_run_at') or now
    base = croniter(schedule_cron, last_run_at)
    next_fire = base.get_next(type(now))
    return next_fire <= now


def run_scheduled_scans():
    """Runs every enabled scan in Firestore 'scans' whose cron schedule has fired since its last run."""
    db = firestore.Client()
    now = datetime.datetime.now(datetime.timezone.utc)

    api_key = get_secret("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in Secret Manager. Cannot run scheduled scans.")
        return

    scans_ref = db.collection('scans').where('enabled', '==', True)
    for doc in scans_ref.stream():
        scan = doc.to_dict()
        if not _is_due(scan, now):
            continue

        name = scan.get('name', doc.id)
        logger.info(f"Running scheduled scan '{name}'...")
        try:
            run_scraper_analysis(api_key, scan['analysis_goal'], scan['sites_str'])
        except Exception as e:
            logger.error(f"Scheduled scan '{name}' failed: {e}")
            continue

        doc.reference.update({'last_run_at': now})
        logger.info(f"Scheduled scan '{name}' complete.")
