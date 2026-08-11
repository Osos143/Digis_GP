"""
Phase 2: interactive, triggered by the user submitting KPI thresholds, and
fully re-runnable on its own as many times as they like.

    User enters KPI thresholds -> Evaluate KPI Labels -> Rule-Based Cause
    Matching -> LLM Explanation -> Update Analysis Session

Every step here reads only from the session object Phase 1 already saved
(`session.anomalies`) -- nothing here re-triggers cleaning, statistics, or
anomaly detection, which is the entire point of splitting the pipeline this
way (see the architecture brief's "Reason for This Design").

Solution retrieval is deliberately absent from this pipeline -- it never
existed anywhere in this platform, and this orchestrator doesn't introduce
it. Phase 2 stops at "what caused this, explained in plain language", not
"here's how to fix it".
"""

from __future__ import annotations

from typing import Optional

from netfix_backend.domain.session import SessionStatus
from netfix_backend.services.cause_matching_service import CauseMatchingService
from netfix_backend.services.common import anomaly_id as get_anomaly_id
from netfix_backend.services.llm_explanation_service import LLMExplanationService
from netfix_backend.services.session_service import SessionService
from netfix_backend.services.threshold_evaluation_service import ThresholdEvaluationService


class Phase2Error(Exception):
    pass


class Phase2Orchestrator:
    def __init__(
        self,
        threshold_service: ThresholdEvaluationService,
        cause_matching_service: CauseMatchingService,
        llm_explanation_service: Optional[LLMExplanationService],
        session_service: SessionService,
    ):
        self.threshold_service = threshold_service
        self.cause_matching_service = cause_matching_service
        self.llm_explanation_service = llm_explanation_service
        self.session_service = session_service

    def run(
        self,
        session_id: str,
        thresholds: Optional[dict] = None,
        explain: bool = True,
        anomaly_ids: Optional[list[str]] = None,
    ):
        """`thresholds` -- if given, becomes the session's new thresholds
        (a full or partial override; unspecified KPIs keep the default).
        `explain` -- whether to run the LLM explanation step at all (set
        False to skip it entirely, e.g. no Ollama/Anthropic access available
        yet, or for a fast preview of just the rule matches).
        `anomaly_ids` -- restrict LLM explanation to only these anomalies
        (cost control -- explaining every anomaly on every Phase 2 re-run
        can mean a lot of LLM calls); defaults to every anomaly that got at
        least one matched cause."""
        session = self.session_service.get(session_id)
        if not session.anomalies:
            raise Phase2Error(f"Session '{session_id}' has no anomalies -- Phase 1 must complete first.")

        self.session_service.set_status(session, SessionStatus.PHASE2_RUNNING)

        effective_thresholds = dict(self.threshold_service.get_default_thresholds())
        if thresholds:
            effective_thresholds.update(thresholds)
        session.thresholds = effective_thresholds

        session.evaluated_kpis = self.threshold_service.evaluate(session.anomalies, effective_thresholds)

        session.matched_causes = self.cause_matching_service.match_all(session.anomalies, session.evaluated_kpis)
        session.excluded_reasons = self.cause_matching_service.excluded_reasons

        if explain and self.llm_explanation_service is not None:
            targets = anomaly_ids or [
                aid for aid, result in session.matched_causes.items() if result.get("matched")
            ]
            anomalies_by_id = {}
            for doc in session.anomalies:
                anomalies_by_id[get_anomaly_id(doc)] = doc

            for aid in targets:
                doc = anomalies_by_id.get(aid)
                if doc is None:
                    continue
                matched = session.matched_causes.get(aid, {}).get("matched", [])
                session.llm_explanations[aid] = self.llm_explanation_service.explain(doc, matched)

        self.session_service.set_status(session, SessionStatus.PHASE2_DONE)
        return session
