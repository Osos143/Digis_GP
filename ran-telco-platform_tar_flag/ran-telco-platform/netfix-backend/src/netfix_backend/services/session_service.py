"""
SessionService: the only class that talks to SessionRepository directly.
Every orchestration step (Phase 1, Phase 2) goes through this, not the
repository directly -- keeps persistence concerns in one place and makes it
trivial to add things like optimistic locking or audit logging later
without touching orchestration code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from netfix_backend.domain.session import AnalysisSession, SessionStatus
from netfix_backend.infra.session_repository import SessionRepository


class SessionNotFoundError(Exception):
    pass


class SessionService:
    def __init__(self, repository: SessionRepository):
        self.repository = repository

    def create(self) -> AnalysisSession:
        session = AnalysisSession()
        self.repository.save(session)
        return session

    def get(self, session_id: str) -> AnalysisSession:
        session = self.repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"No session found with id '{session_id}'")
        return session

    def list(self) -> list[AnalysisSession]:
        return self.repository.list()

    def save(self, session: AnalysisSession) -> AnalysisSession:
        session.updated_at = datetime.now(timezone.utc)
        self.repository.save(session)
        return session

    def set_status(self, session: AnalysisSession, status: SessionStatus, error: Optional[str] = None) -> AnalysisSession:
        session.status = status
        session.error = error
        return self.save(session)
