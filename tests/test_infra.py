"""Integration tests for Object Storage Gateway, Speaker Diarization, and Dynamic DB Pool."""

import os
import pytest
from worker.services.storage.storage_manager import StorageGateway
from worker.audit.services.diarization import diarize_audio_recording, Utterance
from worker.audit.agents.role_resolver import resolve_speaker_roles
from worker.core.database import engine


def test_storage_gateway_local_fallback(tmp_path):
    gateway = StorageGateway()
    res = gateway.generate_presigned_upload("call.wav", "audio/wav")
    assert res["storage_backend"] == "local"
    assert "call.wav" in res["storage_uri"]
    assert res["method"] == "POST"


def test_storage_gateway_fetch_file(tmp_path):
    gateway = StorageGateway()
    dummy = tmp_path / "test.mp3"
    dummy.write_text("audio-bytes")
    
    local_uri = f"local://{dummy}"
    resolved = gateway.fetch_file_for_worker(local_uri)
    assert os.path.exists(resolved)
    assert resolved == str(dummy)


def test_diarization_and_role_resolution(tmp_path):
    dummy_file = tmp_path / "meeting.wav"
    dummy_file.write_text("dummy-audio")

    utterances = diarize_audio_recording(str(dummy_file))
    assert len(utterances) >= 2
    assert isinstance(utterances[0], Utterance)
    assert utterances[0].speaker == "Speaker 0"

    role_map = resolve_speaker_roles(utterances)
    assert "Speaker 0" in role_map
    assert "Advisor" in role_map["Speaker 0"] or "Lead" in role_map["Speaker 0"]


def test_database_engine_connection_pooling():
    # Verify engine is alive and operational
    assert engine is not None
    with engine.connect() as conn:
        assert conn is not None

