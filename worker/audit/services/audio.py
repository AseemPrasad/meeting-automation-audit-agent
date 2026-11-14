"""Audio preprocessing, splitting, and duration estimation to bypass 25MB API limits."""

import os
import subprocess
import shutil
from typing import List, Tuple


def get_audio_file_size_mb(file_path: str) -> float:
    """Return size of file in Megabytes."""
    if not os.path.exists(file_path):
        return 0.0
    return os.path.getsize(file_path) / (1024 * 1024)


def split_audio_if_needed(file_path: str, max_chunk_mb: float = 24.0) -> List[Tuple[str, float]]:
    """
    Inspects audio file. If <= 24MB, returns [(file_path, 0.0)] with 0.0 offset.
    If larger, attempts to use ffmpeg (if available) to compress/segment into chunks.
    Returns list of tuples: [(chunk_file_path, start_time_offset_seconds)].
    """
    file_size_mb = get_audio_file_size_mb(file_path)
    if file_size_mb <= max_chunk_mb:
        return [(file_path, 0.0)]

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        # If ffmpeg is not installed on host, return original file as best effort
        return [(file_path, 0.0)]

    # Segment audio into 10-minute (600s) chunks at 16kHz mono (typically ~5-10MB per chunk)
    output_pattern = f"{file_path}_chunk_%03d.mp3"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", file_path,
        "-f", "segment",
        "-segment_time", "600",
        "-c:a", "libmp3lame",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        output_pattern
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=180
        )
        # Collect generated chunks
        dir_name = os.path.dirname(file_path) or "."
        base_prefix = f"{os.path.basename(file_path)}_chunk_"
        generated_chunks = []
        for f in sorted(os.listdir(dir_name)):
            if f.startswith(base_prefix) and f.endswith(".mp3"):
                full_chunk_path = os.path.join(dir_name, f)
                # Calculate time offset from chunk index (chunk_000 is 0s, 001 is 600s, etc.)
                idx_part = f.replace(base_prefix, "").replace(".mp3", "")
                offset_sec = float(int(idx_part)) * 600.0
                generated_chunks.append((full_chunk_path, offset_sec))
        
        if generated_chunks:
            return generated_chunks
    except Exception:
        # Clean up any partial/corrupted chunk slices on error
        try:
            dir_name = os.path.dirname(file_path) or "."
            base_prefix = f"{os.path.basename(file_path)}_chunk_"
            for f in os.listdir(dir_name):
                if f.startswith(base_prefix) and f.endswith(".mp3"):
                    try:
                        os.remove(os.path.join(dir_name, f))
                    except Exception:
                        pass
        except Exception:
            pass

    return [(file_path, 0.0)]

