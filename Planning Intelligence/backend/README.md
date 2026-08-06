# Network Pulse Backend (FastAPI)

This backend exposes the NR5G planning pipeline as HTTP endpoints used by
the NetPulse frontend workspace.

Important design rule: planning logic is not re-implemented here.
`backend/main.py` only orchestrates calls to existing pipeline modules.

## Current architecture

### What this service does

- Loads workbook data (`raw`, `final`, and runtime uploaded/generated workbooks).
- Runs full planning (`bulk_plan`) when requested.
- Runs targeted planning for add-site and replan-site flows.
- Builds map/KPI payloads for frontend tabs.
- Provides deterministic clash explanations for sectors.
- Provides a tool-calling AI endpoint that is grounded in pipeline outputs.

### Key backend modules

- `main.py`: FastAPI routes, request/response wiring.
- `workbooks.py`: in-memory workbook registry with stable ids (`raw`, `final`, and `live:*`).
- `cache.py`: mtime-keyed cache for pipeline state and network JSON.
- `agent.py`: tool-calling agent loop and tool implementations.
- `pipeline/*`: planning/validation/export logic used by both Streamlit and API paths.

## Workbook model and lifecycle

The backend is stateless in HTTP, but keeps a runtime in-memory workbook registry:

- `raw`: shipped unplanned workbook.
- `final`: shipped planned workbook.
- `live:xxxxxxxx`: runtime-generated ids for uploaded or newly exported workbooks.

Notes:

- `live:*` ids do not persist across backend restarts.
- If a client sends an unknown/stale workbook id, API returns `404` with a
	friendly message.
- Frontend listens for this and redirects users back to Upload and Plan.

## Run locally

### 1) Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2) Start API

```bash
uvicorn main:app --reload --port 8000
```

### CPU Ollama workflow on Windows

If local GPU inference crashes, use the bundled PowerShell launchers:

```powershell
./start-ollama-cpu.ps1
```

In a second terminal:

```powershell
./start-backend-cpu-ollama.ps1
```

This runs Ollama on `http://127.0.0.1:11435` with `OLLAMA_LLM_LIBRARY=cpu`
and starts the backend with `OLLAMA_URL` pointed at that host.

### 3) Verify

- Health: `http://localhost:8000/api/health`
- Swagger: `http://localhost:8000/docs`

## Environment configuration

Optional environment variables used by the AI agent:

- `OLLAMA_URL` (default: `http://127.0.0.1:11435`)
- `OLLAMA_MODEL` (default: `qwen3:4b`)
- `CLAUDE_MODEL` and `ANTHROPIC_API_KEY` exist in code, but current
	public route uses Ollama path only (see AI section below).

## API reference

All endpoints are under `/api`.

### Workbook and dataset endpoints

- `GET /api/workbooks`
	- Returns selectable workbook ids and labels.

- `POST /api/upload` (raw workbook)
	- Form-data: `file` (`.xlsx`/`.xlsm`)
	- Validates workbook shape for planning flow.
	- Rejects already fully planned workbooks.
	- Returns `{ workbook, label, sectors, sites }`.

- `POST /api/upload_final` (already-planned workbook)
	- Form-data: `file` (`.xlsx`/`.xlsm`)
	- Loads workbook as-is, validates KPIs, no replanning.
	- Rejects workbooks with missing PCI assignments.
	- Returns `{ workbook, label, sectors, sites, pass, collisions, confusions, mod3 }`.

- `GET /api/download?workbook=<id>`
	- Downloads workbook file for selected id.

### Planning and network data endpoints

- `POST /api/replan?workbook=<id>`
	- Runs full end-to-end planning (`bulk_plan` + `validate` + `export_results`).
	- Registers output as new `live:*` workbook.
	- Returns `{ workbook, written, pass, collisions, confusions, mod3 }`.

- `GET /api/network?workbook=<id>`
	- Returns full network payload used by Planning/Clashes views.
	- Includes KPI summary enrichment fallback logic.

- `GET /api/raw?workbook=<id>`
	- Returns raw/unplanned network payload shape.

- `GET /api/sectors?workbook=<id>`
	- Returns flattened sector rows with clash flags.
	- Used by Assignments and Clashes tab tooling.

- `GET /api/sectors_raw?workbook=<id>`
	- Returns raw flat sector rows without validation requirement.
	- Includes unplanned rows (`pci/mod4/rsi` can be null).
	- Used by Voronoi Compare to avoid hard failures on partial/legacy files.

### Explanation and assistant endpoints

- `GET /api/explain/{sector_id}?workbook=<id>`
	- Deterministic sector conflict explanation from pipeline graph/rules.

- `POST /api/chat`
	- Body: `{ workbook, message }`
	- Returns simple assistant response from `assistant_chat.answer`.

### AI agent endpoints

- `GET /api/agent/tools`
	- Returns available tool names/descriptions.

- `GET /api/agent/info`
	- Returns active model/url metadata (from backend config).

- `POST /api/agent/chat`
	- Body: `{ workbook, message, model, history }`
	- Current behavior: request is handled by Ollama tool-calling path.
	- Tool outputs are computed by backend functions, model only phrases response.

### Clash definition endpoints

- `GET /api/clash_info`
	- Static dictionary of clash types (severity, threshold, rule text).

- `GET /api/clash_info/{sector_id}?workbook=<id>`
	- Static definition + live sector-specific cause details.

### Add Site workflows

- `POST /api/addsite/new/preview?workbook=<id>`
	- Body: `{ site_id, lat, lon, azimuths }`
	- Builds preview workbook, computes assignments and neighbor context.

- `POST /api/addsite/new/commit`
	- Body: `{ tmp_id, assignments }`
	- Validates + exports live workbook from preview.

- `POST /api/replan_site/preview`
	- Body: `{ workbook, target_site }`
	- Replans sectors for an existing site only.
	- Returns the current plan, replanned assignments, neighbor context, and editor options for guided manual adjustment.

- `POST /api/replan_site/options`
	- Body: `{ workbook, target_site, assignments, mod3_choices }`
	- Recomputes editor options for the current existing-site replan draft.
	- Filters valid PCI values according to the currently chosen Mod4 and Mod3 for each sector.

- `POST /api/replan_site/commit`
	- Body: `{ workbook, assignments }`
	- Validates + exports live workbook with committed site changes.

### Health

- `GET /api/health` -> `{ "status": "ok" }`

## KPI summary behavior

`/api/network` and `/api/raw` call `_enrich_kpi_summary`.

Summary priority:

1. Validator-derived summary (when present in payload).
2. `KPI_Report` sheet summary.
3. Raw fallback summary (`READY`, zeros).

This prevents stale sheet values from overriding fresh validator results.

## Error handling behavior

- Unknown workbook id or missing workbook file returns `404` with a
	user-friendly recovery message.
- Invalid uploads return `400` with specific reason text.
- This behavior is intentionally aligned with frontend event handling for
	stale workbook recovery.

## Relationship to Streamlit implementation

Equivalent concepts:

- `st.session_state["active_xlsx"]` -> explicit `workbook` query/body field.
- `st.cache_resource` -> mtime-keyed cache in `cache.py`.
- Planning and validation rule semantics remain in pipeline modules.

## Typical end-to-end flows

### Raw upload and full planning

1. `POST /api/upload`
2. `POST /api/replan?workbook=<returned_id>`
3. Read results through `GET /api/network`, `GET /api/sectors`, and
	 optional `GET /api/download`.

### Final upload (already planned)

1. `POST /api/upload_final`
2. Read immediately with `GET /api/network`, `GET /api/sectors`.

### Add a brand-new site

1. `POST /api/addsite/new/preview`
2. `POST /api/addsite/new/commit`
3. Consume new returned workbook id.

### Replan existing site

1. `POST /api/replan_site/preview`
2. Optionally call `POST /api/replan_site/options` as the user edits the preview draft.
3. `POST /api/replan_site/commit`
4. Consume new returned workbook id.

The preview editor flow now supports guided manual overrides:

- choose Mod4 first,
- choose Mod3 next,
- receive only PCI values that remain valid for that Mod4/Mod3 combination under the current draft.

## Troubleshooting

- `404` with "file is no longer available": uploaded file or runtime id is stale;
	re-upload workbook and continue.
- Agent returns Ollama unreachable: ensure `ollama serve` is running and
	model from `OLLAMA_MODEL` is pulled.
- Slow first request on a large workbook: expected due to initial load and
	cache warmup.
