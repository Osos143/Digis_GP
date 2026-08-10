"""
MongoDB implementation of SessionRepository. Uses its own collection
(`analysis_sessions`), separate from every collection the existing
ran-anomaly-service / ran-kpi-labeling-service / ran-reason-matching-service
write to -- this keeps the new Session-based architecture additive, not a
replacement for what those services already write, so nothing about running
them standalone (as documented in their own READMEs) breaks.
"""

from __future__ import annotations

from typing import Optional

from pymongo.database import Database

from netfix_backend.domain.session import AnalysisSession
from netfix_backend.infra.session_repository import SessionRepository

SESSIONS_COLLECTION = "analysis_sessions"


class MongoSessionRepository(SessionRepository):
    def __init__(self, db: Database):
        self._coll = db[SESSIONS_COLLECTION]
        self._coll.create_index("session_id", unique=True)

    def save(self, session: AnalysisSession) -> None:
        doc = session.to_doc()
        self._coll.replace_one({"session_id": session.session_id}, doc, upsert=True)

    def get(self, session_id: str) -> Optional[AnalysisSession]:
        doc = self._coll.find_one({"session_id": session_id})
        return AnalysisSession.from_doc(doc) if doc else None

    def list(self) -> list[AnalysisSession]:
        return [AnalysisSession.from_doc(doc) for doc in self._coll.find().sort("created_at", -1)]

    def delete(self, session_id: str) -> None:
        self._coll.delete_one({"session_id": session_id})
