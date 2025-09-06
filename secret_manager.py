import os
from google.cloud import secretmanager

def get_secret(secret_id, project_id=None):
    """Access a secret from Google Secret Manager."""
    if project_id is None:
        # Fallback to environment variables for project ID
        project_id = os.environ.get("GCP_PROJECT") or os.environ.get("DEVSHELL_PROJECT_ID") or "vectr-ai-470202"

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(name=name)
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        # In a production environment, you would want to handle this error more gracefully
        # For example, by logging it and returning a default value or raising an exception
        print(f"Error accessing secret {secret_id}: {e}")
        return None
