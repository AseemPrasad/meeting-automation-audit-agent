"""Async job endpoints.

POST /api/v1/transcripts/process  -> 202 Accepted with job_id
GET  /api/v1/jobs/{job_id}        -> status + result (polling)

Both routes require a valid Bearer token (tenant-scoped). Jobs are created and
queried within the caller's tenant so tenants can never see each other's data.
"""
import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from worker.core.database import SessionLocal, init_db
from worker.core.security import get_current_user, Principal
from worker.models.job import Job
from worker.workflows.transcript_workflow import process_transcript

router = APIRouter(prefix="/api/v1", tags=["jobs"])

init_db()  # ensure the jobs table exists on import


@router.post("/transcripts/process", status_code=202)
async def process_transcript_async(
    file: UploadFile = File(...),
    principal: Principal = Depends(get_current_user),
):
    """Validate upload, persist a PENDING job, enqueue it, return job_id."""
    if not file.filename:
        raise HTTPException(status_code=422, detail="Missing filename")

    # Simple extension guard (accept common audio/video containers)
    allowed = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".webm", ".flac", ".aac"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(allowed)}",
        )

    # Persist a unique temp file so concurrent uploads never collide
    job_id = str(uuid.uuid4())
    safe_name = f"{job_id}_{os.path.basename(file.filename)}"
    file_path = os.path.join("temp", safe_name)
    os.makedirs("temp", exist_ok=True)

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Empty file")

    with open(file_path, "wb") as f:
        f.write(contents)

    db = SessionLocal()
    try:
        job = Job(
            id=job_id,
            tenant_id=principal.tenant_id,
            status="PENDING",
            input_payload=json.dumps({"filename": file.filename}),
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    # Enqueue for background execution (the 202 is returned immediately)
    process_transcript.delay(job_id, file_path)

    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "PENDING"},
    )


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    principal: Principal = Depends(get_current_user),
):
    """Return job status and result payload once completed (tenant-scoped)."""
    db = SessionLocal()
    try:
        job = (
            db.query(Job)
            .filter(Job.id == job_id, Job.tenant_id == principal.tenant_id)
            .first()
        )
    finally:
        db.close()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }

    if job.status == "COMPLETED" and job.result_payload:
        try:
            response["result"] = json.loads(job.result_payload)
        except json.JSONDecodeError:
            response["result"] = job.result_payload
    if job.status == "FAILED":
        response["error"] = job.error

    return response
