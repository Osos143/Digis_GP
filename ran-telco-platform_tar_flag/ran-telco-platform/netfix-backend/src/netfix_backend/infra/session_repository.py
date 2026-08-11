"""
Repository interface for AnalysisSession persistence. Services depend on
this abstraction, not on MongoDB directly -- this is the dependency
inversion that keeps SessionService (and everything built on it) testable
without a real database (see InMemorySessionRepository, used by the test
suite / anywhere a Mongo connection isn't available or wanted).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from netfix_backend.domain.session import AnalysisSession


class SessionRepository(ABC):
    @abstractmethod
    def save(self, session: AnalysisSession) -> None:
        """Insert or fully overwrite the stored session with this one."""
        ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[AnalysisSession]:
        ...

    @abstractmethod
    def list(self) -> list[AnalysisSession]:
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        ...


class InMemorySessionRepository(SessionRepository):
    """No external dependencies -- used for unit tests and for running the
    CLI/API without MongoDB configured. Data doesn't survive a process
    restart, which is the one real trade-off versus MongoSessionRepository."""

    def __init__(self):
        self._sessions: dict[str, AnalysisSession] = {}

    def save(self, session: AnalysisSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[AnalysisSession]:
        return self._sessions.get(session_id)

    def list(self) -> list[AnalysisSession]:
        return list(self._sessions.values())

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
