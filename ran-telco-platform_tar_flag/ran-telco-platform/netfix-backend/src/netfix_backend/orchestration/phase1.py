"""
Phase 1: automatic, runs once per uploaded dataset, ends in a WAIT state.

    Upload PKL -> Cleaning -> Statistics Generation -> Anomaly Detection
    -> Save Analysis Session -> WAIT

No thresholds, no cause matching, no LLM calls happen here -- this
orchestrator's only job is to run each service in order and fold its output
into the session, stopping (status = PHASE1_DONE) once anomalies are
detected and the session is persisted. Phase 2 is a completely separate
orchestrator (phase2.py) that only ever reads what this one wrote.
"""

from __future__ import annotations

from netfix_backend.domain.session import AnalysisSession, SessionStatus
from netfix_backend.services.cleaning_service import CleaningService
from netfix_backend.services.detection_service import DetectionService
from netfix_backend.services.session_service import SessionService
from netfix_backend.services.statistics_service import StatisticsService
from netfix_backend.services.upload_service import UploadService


class Phase1Error(Exception):
    pass


class Phase1Orchestrator:
    def __init__(
        self,
        upload_service: UploadService,
        cleaning_service: CleaningService,
        detection_service: DetectionService,
        statistics_service: StatisticsService,
        session_service: SessionService,
        mongo_uri: str,
        mongo_db: str,
        output_root: str = "netfix_data/outputs",
    ):
        self.upload_service = upload_service
        self.cleaning_service = cleaning_service
        self.detection_service = detection_service
        self.statistics_service = statistics_service
        self.session_service = session_service
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.output_root = output_root

    def run(self, source_path: str, filename: str | None = None):
        """Synchronous full run: create session + save upload + process.
        Used by the CLI. The API uses start() + process() instead so the
        long pipeline can run in a background thread."""
        session = self.start(source_path, filename)
        return self.process(session.session_id)

    def start(self, source_path: str, filename: str | None = None) -> AnalysisSession:
        """Create the session, mark it running, and save the upload to the
        shared input path. Fast -- the API calls this, returns the session
        summary immediately, then runs process() in the background."""
        session = self.session_service.create()
        output_dir = f"{self.output_root}/{session.session_id}"
        self.session_service.set_status(session, SessionStatus.PHASE1_RUNNING)
        session.current_stage = "uploaded"
        session.stage_message = "File upload received. Preparing pipeline..."

        session.dataset = self.upload_service.save_upload(session.session_id, source_path, filename)
        self.session_service.save(session)
        return session

    def process(self, session_id: str) -> AnalysisSession:
        """Run cleaning + detection + statistics for an existing session.
        Safe to call from a background thread; updates the session in Mongo
        as it progresses."""
        session = self.session_service.get(session_id)
        output_dir = f"{self.output_root}/{session.session_id}"

        try:
            # Stage 1: Cleaning & Profiling
            session.current_stage = "cleaning"
            session.stage_message = "Stage 1/2: Cleaning and profiling drive-test dataset..."
            self.session_service.save(session)

            clean_result = self.cleaning_service.run(output_dir)
            if not clean_result["success"]:
                raise Phase1Error(f"Cleaning failed (returncode={clean_result['returncode']}): "
                                   f"{clean_result['stderr_tail']}")
            session.dataset["cleaning"] = clean_result

            # Ensure Python sample count is stored in session metadata
            if "sample_count" not in session.dataset or not session.dataset["sample_count"]:
                from netfix_backend.services.upload_service import count_pkl_samples
                raw_path = session.dataset.get("path") or "/data/raw/Network_Drive_Test.pkl"
                count = count_pkl_samples(raw_path)
                if count > 0:
                    session.dataset["sample_count"] = count
                    session.dataset["total_rows"] = count

            # Stage 2: Anomaly Detection
            session.current_stage = "detecting_anomalies"
            session.stage_message = "Stage 2/2: Running 19-stage statistical & ML anomaly detection engine..."
            self.session_service.save(session)

            detect_result = self.detection_service.run(output_dir, self.mongo_uri, self.mongo_db)
            if not detect_result["success"]:
                raise Phase1Error(f"Anomaly detection failed (returncode={detect_result['returncode']}): "
                                   f"{detect_result['stderr_tail']}")
            session.dataset["detection_run_id"] = detect_result["run_id"]
            session.anomalies = detect_result["anomalies"]

            session.statistics = self.statistics_service.compute(session.anomalies)

            session.current_stage = "phase1_done"
            session.stage_message = f"Pipeline finished successfully! {len(session.anomalies)} anomalies detected."
            self.session_service.set_status(session, SessionStatus.PHASE1_DONE)
            self.session_service.save(session)
            return session

        except Phase1Error as e:
            session.current_stage = "failed"
            session.stage_message = f"Pipeline failed: {str(e)}"
            self.session_service.set_status(session, SessionStatus.FAILED, error=str(e))
            self.session_service.save(session)
            raise
