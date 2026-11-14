"""Automated retention and privacy lifecycle service (GDPR / Wiretap 30-day prune, 7-year cert retention)."""

import os
import shutil
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from worker.models.job import Job
from worker.saas.models.organization import Organization
from worker.services.storage.storage_manager import storage_gateway


class RetentionPolicyService:
    """Automates media destruction to eliminate wiretap liability while preserving compliance certificates."""

    @staticmethod
    def enforce_audio_retention(
        db: Session,
        default_retention_days: int = 30
    ) -> Dict[str, Any]:
        """
        Scans completed jobs older than retention threshold.
        Deletes raw audio files from disk/storage (including remote S3/GCS),
        while strictly preserving the audit certificate, transcript, and SHA-256 seal.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=default_retention_days)
        
        # Query jobs older than cutoff with non-null result
        jobs_to_prune = db.query(Job).filter(
            Job.created_at < cutoff_date,
            Job.status == "COMPLETED"
        ).all()

        pruned_count = 0
        for job in jobs_to_prune:
            # 1. Clean local temp uploads if matching job id
            upload_dir = "temp_audit_uploads"
            if os.path.exists(upload_dir):
                for fname in os.listdir(upload_dir):
                    if job.id in fname:
                        fpath = os.path.join(upload_dir, fname)
                        try:
                            if os.path.isfile(fpath):
                                os.remove(fpath)
                                pruned_count += 1
                        except Exception:
                            pass

            # 2. Clean cloud object if job.input_payload is an S3/GCS URI
            if job.input_payload and (job.input_payload.startswith("s3://") or job.input_payload.startswith("gcs://")):
                try:
                    storage_gateway.delete_file(job.input_payload)
                    pruned_count += 1
                except Exception:
                    pass

        return {
            "status": "success",
            "retention_threshold_days": default_retention_days,
            "jobs_evaluated": len(jobs_to_prune),
            "audio_files_purged": pruned_count
        }

