"""
Minimal MongoDB writer.

Every JSON file the pipeline writes to disk is, unchanged, ALSO written to a
MongoDB collection of the same name (extension stripped). This is purely
additive: the on-disk JSON file is still written exactly as before, in the
same place, with the same content. Mongo is best-effort -- if MONGO_URI is
not set, pymongo isn't installed, or the write fails for any reason, this
prints a warning and returns without raising, so a Mongo outage can never
break a pipeline run or change its file outputs.

Configuration (environment variables):
  MONGO_URI   e.g. mongodb://mongo:27017  (unset = Mongo disabled)
  MONGO_DB    default: "ran_telco"
  RAN_RUN_ID  tags every document with the run that produced it
              (set automatically by run_pipeline.py if not already set)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Union

_client = None  # reused across the many write_json_to_mongo() calls in one run


def _get_client():
    global _client
    if _client is not None:
        return _client
    mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        return None
    try:
        from pymongo import MongoClient
    except ImportError:
        print("[mongo] pymongo not installed; skipping MongoDB writes.", file=sys.stderr)
        return None
    try:
        _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        return _client
    except Exception as e:
        print(f"[mongo] WARNING: could not connect to {mongo_uri}: {e}", file=sys.stderr)
        _client = None
        return None


def write_json_to_mongo(collection_name: str, records: Union[dict, Iterable[dict]]) -> None:
    """Insert the same records that were just written to a JSON file into MongoDB.

    Safe to call unconditionally -- does nothing if Mongo isn't configured/reachable.
    """
    client = _get_client()
    if client is None:
        return

    if isinstance(records, dict):
        records = [records]
    records = list(records)
    if not records:
        print(f"[mongo] no records to write for '{collection_name}'.")
        return

    try:
        db_name = os.environ.get("MONGO_DB", "ran_telco")
        coll = client[db_name][collection_name]
        run_id = os.environ.get("RAN_RUN_ID", "unknown_run")
        ingested_at = datetime.now(timezone.utc)
        docs = []
        for rec in records:
            doc: dict[str, Any] = dict(rec)
            doc["_run_id"] = run_id
            doc["_ingested_at"] = ingested_at
            docs.append(doc)
        coll.insert_many(docs)
        print(f"[mongo] wrote {len(docs)} documents to {db_name}.{collection_name}")
    except Exception as e:
        print(f"[mongo] WARNING: failed to write to '{collection_name}': {e}", file=sys.stderr)
