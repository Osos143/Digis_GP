"""
DetectionService: wraps `ran-anomaly` (ran-anomaly-service), unchanged, for
the same reason CleaningService wraps `ran-clean` -- its 19 stages are
`exec()`'d slices of one monolithic script, not composable functions.

After the subprocess completes, this service reads the anomaly documents it
just wrote back out of MongoDB (from `rca_anomaly_incidents_full_compact`
only -- the collection this whole platform's reason-matching work already
settled on, see ran-reason-matching-service's mongo_io.py) and returns them
so Phase 1 can embed them directly into the Analysis Session. This is the
one and only place ran-anomaly-service's pipeline is triggered -- Phase 2
never calls this again.
"""

from __future__ import annotations

import selectors
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from pymongo.database import Database

ANOMALY_COLLECTION = "rca_anomaly_incidents_full_compact"


def _run_with_logging(cmd: list[str], log_path: Path) -> tuple[int, str, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    with open(log_path, "w", encoding="utf-8") as f:
        header = f"=== Executing: {' '.join(cmd)} ===\n"
        sys.stdout.write(header)
        sys.stdout.flush()
        f.write(header)
        f.flush()

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )
        sel = selectors.DefaultSelector()
        if proc.stdout:
            sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
        if proc.stderr:
            sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")

        while sel.get_map():
            events = sel.select(timeout=0.1)
            for key, _ in events:
                stream = key.fileobj
                line = stream.readline()
                if not line:
                    sel.unregister(stream)
                    continue
                if key.data == "stdout":
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    stdout_lines.append(line)
                else:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                    stderr_lines.append(line)
                f.write(line)
                f.flush()

        returncode = proc.wait()

    return returncode, "".join(stdout_lines), "".join(stderr_lines)


def find_latest_run_id(db: Database) -> Optional[str]:
    doc = db[ANOMALY_COLLECTION].find_one(sort=[("_ingested_at", -1)])
    return doc.get("_run_id") if doc else None


class DetectionService:
    def __init__(self, db: Database, command: str = "ran-anomaly"):
        self.db = db
        self.command = command

    def run(self, output_dir: str, mongo_uri: str, mongo_db: str) -> dict[str, Any]:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        log_file = out_path / "ran_anomaly.log"

        returncode, stdout, stderr = _run_with_logging(
            [self.command, "--output-dir", output_dir, "--mongo-uri", mongo_uri, "--mongo-db", mongo_db],
            log_file,
        )
        success = returncode == 0
        outcome: dict[str, Any] = {
            "success": success,
            "returncode": returncode,
            "output_dir": str(out_path.resolve()),
            "log_file": str(log_file.resolve()),
            "stdout_tail": "\n".join(stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(stderr.splitlines()[-30:]) if not success else "",
            "run_id": None,
            "anomalies": [],
        }
        if not success:
            return outcome

        run_id = find_latest_run_id(self.db)
        outcome["run_id"] = run_id
        if run_id:
            query = {"_run_id": run_id}
        else:
            query = {}  # fall back to "everything in the collection" if _run_id tagging is ever absent
        anomalies = list(self.db[ANOMALY_COLLECTION].find(query))
        for doc in anomalies:
            doc["_id"] = str(doc["_id"])  # keep the session JSON-serializable
        outcome["anomalies"] = anomalies
        return outcome
