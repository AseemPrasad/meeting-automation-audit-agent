"""
Secrets and configuration resolver with automatic fallback.
Supports local environment variables (.env), AWS Secrets Manager, and GCP Secret Manager.
"""

import os
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SECRETS_CACHE: dict[str, Any] = {}
_AWS_SECRETS_LOADED: bool = False
_GCP_SECRETS_LOADED: bool = False


def _load_aws_secrets() -> None:
    global _AWS_SECRETS_LOADED
    if _AWS_SECRETS_LOADED:
        return
    _AWS_SECRETS_LOADED = True

    secret_name = os.environ.get("AWS_SECRETS_MANAGER_SECRET_ID")
    if not secret_name:
        return

    try:
        import boto3
        from botocore.exceptions import ClientError

        region = os.environ.get("AWS_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            payload = json.loads(response["SecretString"])
            if isinstance(payload, dict):
                _SECRETS_CACHE.update(payload)
                logger.info(f"Loaded {len(payload)} secrets from AWS Secrets Manager ({secret_name})")
    except Exception as e:
        logger.warning(f"Could not load secrets from AWS Secrets Manager ({secret_name}): {e}")


def _load_gcp_secrets() -> None:
    global _GCP_SECRETS_LOADED
    if _GCP_SECRETS_LOADED:
        return
    _GCP_SECRETS_LOADED = True

    project_id = os.environ.get("GCP_SECRET_MANAGER_PROJECT_ID")
    secret_name = os.environ.get("GCP_SECRET_MANAGER_SECRET_NAME")
    if not project_id or not secret_name:
        return

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload_str = response.payload.data.decode("UTF-8")
        payload = json.loads(payload_str)
        if isinstance(payload, dict):
            _SECRETS_CACHE.update(payload)
            logger.info(f"Loaded secrets from GCP Secret Manager ({name})")
    except Exception as e:
        logger.warning(f"Could not load secrets from GCP Secret Manager: {e}")


def get_secret(key: str, default: Optional[Any] = None) -> Any:
    """
    Resolves configuration secret with hierarchical fallback:
    1. OS / .env Environment Variables
    2. Dynamic Cloud Cache (AWS Secrets Manager / GCP Secret Manager)
    3. Provided default value
    """
    # 1. Direct environment variable check
    env_val = os.environ.get(key)
    if env_val is not None and env_val != "":
        return env_val

    # 2. Lazy load cloud secrets if configured
    if not _AWS_SECRETS_LOADED and os.environ.get("AWS_SECRETS_MANAGER_SECRET_ID"):
        _load_aws_secrets()

    if not _GCP_SECRETS_LOADED and os.environ.get("GCP_SECRET_MANAGER_PROJECT_ID"):
        _load_gcp_secrets()

    if key in _SECRETS_CACHE:
        return _SECRETS_CACHE[key]

    return default

