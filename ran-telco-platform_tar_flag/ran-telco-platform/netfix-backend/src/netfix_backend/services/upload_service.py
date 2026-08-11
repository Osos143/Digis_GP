"""
UploadService: saves an uploaded .pkl dataset to the standard input path that
ran-clean reads from by default (/data/raw/Network_Drive_Test.pkl). The
uploaded file always lands at that fixed location -- each upload overwrites
the previous one.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_INPUT_PATH = Path("/data/raw/Network_Drive_Test.pkl")


def count_pkl_samples(file_path: Path | str) -> int:
    """Python helper function to count the exact number of telemetry samples (rows) in a .pkl file."""
    p = Path(file_path)
    if not p.exists():
        return 0
    try:
        import pandas as pd
        df = pd.read_pickle(p)
        if hasattr(df, "shape"):
            return int(df.shape[0])
    except Exception:
        try:
            import pickle
            with open(p, "rb") as f:
                data = pickle.load(f)
                if hasattr(data, "shape"):
                    return int(data.shape[0])
                elif isinstance(data, (list, tuple, dict)):
                    return len(data)
        except Exception:
            pass
    return 0


class UploadService:
    def __init__(self, base_dir: str = "netfix_data/uploads"):
        self.base_dir = Path(base_dir)

    def save_upload(self, session_id: str, source_path: str, filename: str | None = None) -> dict[str, Any]:
        """Copies the uploaded file to the default ran-clean input path so
        that the cleaning service always finds it at the expected location."""
        filename = filename or Path(source_path).name
        
        raw_env_path = os.environ.get("RAN_CLEAN_INPUT_FILE", "/data/raw/Network_Drive_Test.pkl")
        target_path = Path(raw_env_path)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path = target_path
        except (PermissionError, OSError):
            fallback_dir = Path("./Raw_Data")
            fallback_dir.mkdir(parents=True, exist_ok=True)
            dest_path = fallback_dir / "Network_Drive_Test.pkl"

        # shutil.copyfile streams in chunks (64 KiB buffer)
        shutil.copyfile(source_path, dest_path)

        # Count exact telemetry sample rows from the uploaded dataset file using Python
        sample_count = count_pkl_samples(dest_path) or count_pkl_samples(source_path)

        return {
            "filename": filename,
            "path": str(dest_path.resolve()),
            "size_bytes": dest_path.stat().st_size,
            "sample_count": sample_count,
            "total_rows": sample_count,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
