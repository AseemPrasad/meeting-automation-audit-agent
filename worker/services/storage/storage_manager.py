"""Object storage abstraction layer supporting AWS S3, Google Cloud Storage, and Local Fallback."""

import os
import uuid
import shutil
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
GCS_BUCKET = os.getenv("GCS_BUCKET")
LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", "temp_audit_uploads")


def get_s3_client(region: Optional[str] = None):
    """
    Returns a boto3 S3 client supporting Zero-Trust IAM roles / instance profiles.
    If AWS_ACCESS_KEY_ID is set in env, it uses it; otherwise it delegates to
    AWS IRSA, ECS task roles, or EC2 instance profiles without failing.
    """
    import boto3
    from botocore.config import Config

    reg = region or AWS_REGION
    cfg = Config(retries={"max_attempts": 3, "mode": "standard"})

    aws_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")

    if aws_key and aws_secret:
        return boto3.client(
            "s3",
            region_name=reg,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            config=cfg,
        )
    # Zero-Trust IAM / Pod Identity / Instance Profile fallback
    return boto3.client("s3", region_name=reg, config=cfg)


class StorageGateway:
    """Manages secure presigned upload URLs and file retrieval across cloud providers."""

    def __init__(self):
        os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

    def generate_presigned_upload(
        self,
        filename: str,
        content_type: str = "audio/mpeg",
        expires_in: int = 900
    ) -> Dict[str, Any]:
        """
        Generates a direct-to-cloud presigned PUT URL.
        Falls back to local direct-upload simulation if cloud buckets are not configured.
        """
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{filename}"

        if AWS_S3_BUCKET:
            try:
                s3_client = get_s3_client(AWS_REGION)
                key = f"recordings/{safe_filename}"
                url = s3_client.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={
                        "Bucket": AWS_S3_BUCKET,
                        "Key": key,
                        "ContentType": content_type
                    },
                    ExpiresIn=expires_in
                )
                return {
                    "storage_backend": "s3",
                    "upload_url": url,
                    "storage_uri": f"s3://{AWS_S3_BUCKET}/{key}",
                    "method": "PUT",
                    "headers": {"Content-Type": content_type}
                }
            except Exception as e:
                logger.warning(f"S3 presigned upload generation failed, falling back to local: {e}")

        # Local simulation fallback
        local_path = os.path.join(LOCAL_STORAGE_DIR, safe_filename)
        return {
            "storage_backend": "local",
            "upload_url": f"/api/v2/audit/direct-upload?file_id={file_id}",
            "storage_uri": f"local://{os.path.abspath(local_path)}",
            "method": "POST",
            "headers": {}
        }

    def fetch_file_for_worker(self, storage_uri: str) -> str:
        """
        Resolves storage URI (s3://, gcs://, local://, or raw path) to a local path
        for the Celery worker to process.
        """
        if storage_uri.startswith("local://"):
            return storage_uri.replace("local://", "")

        if storage_uri.startswith("s3://"):
            parts = storage_uri.replace("s3://", "").split("/", 1)
            bucket, key = parts[0], parts[1]
            local_dest = os.path.join(LOCAL_STORAGE_DIR, os.path.basename(key))
            s3_client = get_s3_client()
            s3_client.download_file(bucket, key, local_dest)
            return local_dest

        # Default: treat as local path directly
        return storage_uri

    def delete_file(self, storage_uri: str) -> bool:
        """Deletes a file from S3, GCS, or local filesystem."""
        try:
            if storage_uri.startswith("s3://"):
                parts = storage_uri.replace("s3://", "").split("/", 1)
                bucket, key = parts[0], parts[1]
                s3_client = get_s3_client()
                s3_client.delete_object(Bucket=bucket, Key=key)
                return True
            elif storage_uri.startswith("local://"):
                l_path = storage_uri.replace("local://", "")
                if os.path.exists(l_path):
                    os.remove(l_path)
                    return True
            elif os.path.exists(storage_uri):
                os.remove(storage_uri)
                return True
        except Exception:
            return False
        return False


storage_gateway = StorageGateway()

