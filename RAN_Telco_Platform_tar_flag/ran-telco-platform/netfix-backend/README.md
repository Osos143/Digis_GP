# netfix-backend

The NetFix two-phase orchestration backend. Sits on top of the platform's
existing, independently-working services (`ran-cleaning-service`,
`ran-anomaly-service`, `ran-kpi-labeling-service`'s thresholding logic,
`ran-reason-matching-service`'s LLM-explanation logic) and reorganizes them
into two phases built around one persistent **Analysis Session**, instead of
each stage writing to its own disconnected files/collections.

None of those four services were rewritten. See each service's own file
docstrings in `services/*.py` for exactly what's reused from which one, and
why the integration takes the shape it does (subprocess for the two
exec()-based pipelines, direct Python import for the two pure-function ones).

## Architecture

### Phase 1 -- automatic, runs once per uploaded dataset

```
Upload PKL -> Cleaning -> Statistics Generation -> Anomaly Detection
           -> Save Analysis Session -> WAIT
```

No thresholds, no cause matching, no LLM calls happen here. Ends with the
session in `PHASE1_DONE` status: anomalies detected, statistics computed,
cleaned dataset produced, session persisted.

**Why anomaly detection only ever runs once:** `ran-anomaly-service`'s 19
stages are `exec()`'d slices of one monolithic script sharing a namespace,
not composable functions -- there's no way to invoke "just the statistics
part" independently of the full detection run. So `DetectionService` and
`StatisticsService` are two separate classes with two separate
responsibilities (triggering vs. summarizing), but they're both downstream
of the *same single* `ran-anomaly` subprocess call. That satisfies the real
requirement -- the expensive computation runs once -- without needing to
perform surgery on already-verified pipeline code.

### Phase 2 -- interactive, fully re-runnable

```
User enters KPI thresholds -> Evaluate KPI Labels -> Rule-Based Cause
Matching -> LLM Explanation -> Update Analysis Session
```

Every step here reads only `session.anomalies`, already sitting in the
session from Phase 1. Re-running Phase 2 with different thresholds -- as
many times as the user likes -- never touches cleaning, statistics, or
anomaly detection.

**Cause matching is deterministic, not RAG.** This is the one substantive
change from an earlier version of this platform's reason-matching service:
matching now works by comparing an anomaly's evaluated KPI label (or, for
boolean conditions, its raw value) against an explicit condition per reason
-- no embeddings, no LLM call, no Ollama dependency for this step at all.
See `rules/condition_catalog.py` for the full reasoning and the exact list
of which of the 34 taxonomy reasons are evaluable vs. explicitly excluded
(with why) given the KPI fields this platform's anomaly pipeline actually
produces.

**Solution retrieval does not exist anywhere in this codebase.** It was
never part of the platform before this refactor, and this refactor doesn't
introduce it -- Phase 2 stops at "what caused this, explained in plain
language," not "here's how to fix it."

## The Analysis Session

One object per uploaded dataset, created at the start of Phase 1 and updated
(never replaced) by every subsequent stage:

```json
{
  "session_id": "session_...",
  "status": "phase1_done",
  "dataset": {"filename": "...", "path": "...", "cleaning": {...}, "detection_run_id": "..."},
  "statistics": {"total_anomalies": 42, "by_severity": {...}, "kpi_summary": {...}},
  "anomalies": [ /* full rca_anomaly_incidents_full_compact documents */ ],
  "thresholds": {"rsrp_median_dbm": {"poor_threshold": -110, ...}, ...},
  "evaluated_kpis": {"INC-0017": {"rsrp_median_dbm": {"value": -118, "label": "poor"}, ...}, ...},
  "matched_causes": {"INC-0017": {"matched": [{"reason_id": "low_rsrp", "title": "...", ...}]}, ...},
  "excluded_reasons": [{"reason_id": "early_ho", "why": "No handover-type classification field exists..."}],
  "llm_explanations": {"INC-0017": {"text": "...", "key_evidence": [...], "model": "llama3.1"}}
}
```

Persisted in its own MongoDB collection (`analysis_sessions`) -- separate
from every collection the other four services write to, so nothing about
running them standalone (as documented in their own READMEs) is affected by
this refactor.

## Project layout

```
netfix-backend/
├── pyproject.toml
├── README.md
└── src/netfix_backend/
    ├── domain/session.py            # AnalysisSession model + SessionStatus
    ├── infra/
    │   ├── session_repository.py     # abstract interface + InMemorySessionRepository (tests)
    │   └── mongo_session_repository.py
    ├── rules/condition_catalog.py    # the rule-based matching core (see above)
    ├── services/
    │   ├── upload_service.py
    │   ├── cleaning_service.py       # wraps `ran-clean` (subprocess)
    │   ├── detection_service.py      # wraps `ran-anomaly` (subprocess) + reads results back from Mongo
    │   ├── statistics_service.py     # pure computation over Phase 1's anomalies
    │   ├── threshold_evaluation_service.py   # reuses ran_kpi_labeling's label_value()
    │   ├── cause_matching_service.py         # the new rule engine
    │   ├── llm_explanation_service.py        # the only LLM call in this backend
    │   └── session_service.py        # the only class that talks to the repository
    ├── orchestration/
    │   ├── phase1.py
    │   └── phase2.py
    ├── bootstrap.py                  # composition root, shared by CLI and API
    ├── cli/main.py
    └── api/main.py
```

## Running it

### Via Docker Compose

```bash
docker compose up -d mongo ollama
docker compose exec ollama ollama pull llama3.1   # first time only -- explanation step needs this

docker compose up -d netfix-backend
# API docs: http://localhost:8000/docs
```

`netfix-backend`'s environment expects `Reasons_Data/throughput_degradation_reasoning_graph.json`
to exist (or point `REASONS_FILE` elsewhere, or upload reasons via
`reason-match upload-reasons` first and unset `REASONS_FILE` -- Phase 2 then
reads whatever's already in MongoDB's `rca_reasons` collection).

**Note:** `ollama` is gated behind the `tools` Compose profile (same as
`kpi-label`/`reason-match`) and won't start with a bare `docker compose up`
-- start it explicitly as shown above, or set `SKIP_LLM=true` on
`netfix-backend` if you only want Phase 2's rule-based matching without any
explanation step.

### Via the CLI (no server needed, same underlying code)

```bash
pip install -e ran-cleaning-service -e ran-anomaly-service -e ran-kpi-labeling-service -e ran-reason-matching-service -e netfix-backend

netfix-backend --reasons-file Reasons_Data/throughput_degradation_reasoning_graph.json upload Raw_Data/Network_Drive_Test.pkl
# -> prints session_id

netfix-backend status <session_id>
netfix-backend thresholds-show <session_id>

netfix-backend phase2 <session_id>                          # defaults: explain every matched anomaly
netfix-backend phase2 <session_id> --no-explain              # rule matching only, no LLM
netfix-backend phase2 <session_id> --anomaly-ids INC-0017    # explain just this one
netfix-backend phase2 <session_id> --thresholds-file my_thresholds.json

netfix-backend explain <session_id> INC-0017                 # regenerate one explanation on demand
```

### Via FastAPI directly

```bash
uvicorn netfix_backend.api.main:app --reload
```

| Method | Path | Phase | What it does |
|---|---|---|---|
| POST | `/sessions` | 1 | Upload a `.pkl`, run clean+detect+stats synchronously, return the session |
| GET | `/sessions` | -- | List all sessions (summaries) |
| GET | `/sessions/{id}` | -- | Get one session (`?full=true` for the complete document) |
| GET | `/sessions/{id}/anomalies` | -- | Just the anomalies list |
| GET | `/sessions/{id}/thresholds` | -- | Current (or default) thresholds |
| POST | `/sessions/{id}/thresholds` | 2 | Submit thresholds, run evaluate+match+explain |
| GET | `/sessions/{id}/causes` | -- | `matched_causes` + `excluded_reasons` |
| POST | `/sessions/{id}/explain` | 2 | Regenerate one anomaly's explanation on demand |

## Testing without MongoDB or Ollama

Every service takes its dependencies through its constructor (plain
dependency injection, no framework). `infra.session_repository.InMemorySessionRepository`
lets `SessionService` (and everything built on it) run without MongoDB at
all; swapping in a fake object with an `.explain()` method in place of
`RuleBasedExplainerLLM` does the same for `LLMExplanationService` without
needing Ollama. See the docstrings in `orchestration/phase1.py` and
`phase2.py` for the exact constructor shape each orchestrator expects.
