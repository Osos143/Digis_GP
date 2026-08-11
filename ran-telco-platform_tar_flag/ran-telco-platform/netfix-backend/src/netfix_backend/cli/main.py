"""
Command-line entry point: netfix-backend

Exists specifically because "the frontend is not implemented yet ... we are
currently building and testing all backend services using the CLI and
FastAPI" -- every operation the API exposes has a CLI equivalent here.

Subcommands:
  upload            Phase 1: upload a .pkl, run cleaning + detection + stats, save the session
  status             show one session (or a summary list of all sessions)
  thresholds show    show the thresholds a session is currently using (or the defaults)
  phase2             Phase 2: submit thresholds (optional), evaluate KPI labels,
                     rule-match causes, generate LLM explanations
  explain            re-run just the LLM explanation step for one specific anomaly
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from netfix_backend.bootstrap import build_context
from netfix_backend.services.session_service import SessionNotFoundError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netfix-backend", description="NetFix backend CLI (Phase 1 + Phase 2).")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGO_DB", "ran_telco"))
    parser.add_argument("--reasons-file", default=os.environ.get("REASONS_FILE"),
                         help="Path to a reasons file (flat list or taxonomy graph). If omitted, reasons "
                              "already uploaded to MongoDB's rca_reasons collection are used instead.")
    parser.add_argument("--llm-provider", default=os.environ.get("LLM_PROVIDER", "ollama"), choices=["ollama", "anthropic"])
    parser.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"))
    parser.add_argument("--ollama-base-url", default=os.environ.get("OLLAMA_BASE_URL"))

    sub = parser.add_subparsers(dest="command", required=True)

    p_upload = sub.add_parser("upload", help="Phase 1: upload + clean + detect + save session.")
    p_upload.add_argument("pkl_path")

    p_status = sub.add_parser("status", help="Show one session's status/summary, or list all sessions.")
    p_status.add_argument("session_id", nargs="?", default=None)
    p_status.add_argument("--full", action="store_true", help="Print the full session document, not just the summary.")

    p_thresh = sub.add_parser("thresholds-show", help="Show current/default thresholds.")
    p_thresh.add_argument("session_id", nargs="?", default=None)

    p_phase2 = sub.add_parser("phase2", help="Phase 2: thresholds -> evaluate -> match -> explain.")
    p_phase2.add_argument("session_id")
    p_phase2.add_argument("--thresholds-file", default=None, help="JSON file: {kpi_id: {poor_threshold, acceptable_threshold, good_threshold}}")
    p_phase2.add_argument("--no-explain", action="store_true")
    p_phase2.add_argument("--anomaly-ids", nargs="+", default=None, help="Only explain these anomaly ids.")

    p_explain = sub.add_parser("explain", help="Generate/regenerate the LLM explanation for one anomaly.")
    p_explain.add_argument("session_id")
    p_explain.add_argument("anomaly_id")

    p_rca = sub.add_parser("rca", help="Run Root Cause Analysis (RCA) matching for an anomaly ID.")
    p_rca.add_argument("session_id")
    p_rca.add_argument("anomaly_id")

    return parser


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    skip_llm = args.command in ("upload", "status", "thresholds-show") or (
        args.command == "phase2" and args.no_explain
    )
    ctx = build_context(
        mongo_uri=args.mongo_uri, mongo_db=args.mongo_db, reasons_file=args.reasons_file,
        llm_provider=args.llm_provider, llm_model=args.llm_model, ollama_base_url=args.ollama_base_url,
        skip_llm=skip_llm,
    )

    try:
        if args.command == "upload":
            session = ctx.phase1.run(args.pkl_path)
            print(f"Session created: {session.session_id}  status={session.status.value}")
            _print_json(session.summary())
            return 0

        if args.command == "status":
            if args.session_id:
                session = ctx.session_service.get(args.session_id)
                _print_json(session.to_doc() if args.full else session.summary())
            else:
                for session in ctx.session_service.list():
                    _print_json(session.summary())
            return 0

        if args.command == "thresholds-show":
            if args.session_id:
                session = ctx.session_service.get(args.session_id)
                thresholds = session.thresholds or ctx.phase2.threshold_service.get_default_thresholds()
            else:
                thresholds = ctx.phase2.threshold_service.get_default_thresholds()
            _print_json(thresholds)
            return 0

        if args.command == "phase2":
            thresholds = None
            if args.thresholds_file:
                with open(args.thresholds_file) as f:
                    thresholds = json.load(f)
            session = ctx.phase2.run(
                args.session_id, thresholds=thresholds, explain=not args.no_explain, anomaly_ids=args.anomaly_ids,
            )
            print(f"Phase 2 complete for {session.session_id}: status={session.status.value}")
            print(f"  matched anomalies : {sum(1 for v in session.matched_causes.values() if v.get('matched'))}"
                  f"/{len(session.matched_causes)}")
            print(f"  excluded reasons  : {len(session.excluded_reasons)}")
            print(f"  explanations      : {len(session.llm_explanations)}")
            return 0

        if args.command == "explain":
            session = ctx.session_service.get(args.session_id)
            matched = session.matched_causes.get(args.anomaly_id, {}).get("matched", [])
            anomaly_doc = next(
                (a for a in session.anomalies if a.get("incident_id") == args.anomaly_id or str(a.get("_id")) == args.anomaly_id),
                None,
            )
            if anomaly_doc is None:
                print(f"ERROR: anomaly '{args.anomaly_id}' not found in session '{args.session_id}'.", file=sys.stderr)
                return 1
            explanation = ctx.phase2.llm_explanation_service.explain(anomaly_doc, matched)
            session.llm_explanations[args.anomaly_id] = explanation
            ctx.session_service.save(session)
            _print_json(explanation)
            return 0

        if args.command == "rca":
            from netfix_backend.services.rca_service import RCAService
            rca_svc = RCAService(mongo_uri=args.mongo_uri, mongo_db=args.mongo_db)
            session = ctx.session_service.get(args.session_id)
            anomalies = getattr(session, 'anomalies', []) or []
            target_anomaly = next((a for a in anomalies if a.get("incident_id") == args.anomaly_id or a.get("id") == args.anomaly_id), None)
            if not target_anomaly:
                try:
                    mongo_client = rca_svc.get_mongo_client()
                    if mongo_client:
                        db = mongo_client[rca_svc.mongo_db_name]
                        query = {"$or": [{"incident_id": args.anomaly_id}, {"id": args.anomaly_id}]}
                        target_anomaly = db["rca_anomaly_incidents_full_compact"].find_one(query) or db["anomalies"].find_one(query)
                        if target_anomaly:
                            target_anomaly.pop("_id", None)
                except Exception:
                    pass
            if not target_anomaly:
                target_anomaly = {"incident_id": args.anomaly_id}
            result = rca_svc.classify_anomaly(target_anomaly)
            _print_json(result)
            return 0

    except SessionNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
