# Frontend (NetFix + NetPulse)

This frontend hosts two workspaces inside one React app shell:

- Drive Test and Anomaly workspace (existing NetFix pages)
- Network Pulse workspace (NR5G PCI/RSI/Mod4 planning)

The workspace is selected from the login screen and routed by `currentView`
in `src/App.tsx`.

## Tech stack

- React 19 + TypeScript + Vite
- Tailwind CSS v4
- Leaflet + react-leaflet (map rendering)
- Recharts (charts used in the original NetFix workspace)

## Quick start

### 1) Install

```bash
cd frontend
npm install
```

### 2) Configure backend URL

Copy `.env.example` to `.env` and set:

```env
VITE_API_URL=http://localhost:8000
```

### 3) Run

```bash
npm run dev
```

Default local UI URL is Vite's dev server output (usually `http://localhost:5173`).

## Workspace behavior

## Login and routing

- Login includes a workspace selector:
  - `Drive Test & Anomaly`
  - `5G Network Planning`
- Selecting `5G Network Planning` routes into NetPulse tabs.
- Sidebar includes `Switch Workspace` to return to login.

## NetPulse runtime state

NetPulse state is persisted in `localStorage`:

- `netpulse-current-view`
- `netpulse-workbook`

If backend reports workbook file loss/staleness, frontend receives
`netpulse:workbook-missing` and auto-resets:

- Clears active workbook id
- Redirects to `Upload & Plan`

## NetPulse tabs and what they do

### 1) Upload & Plan (`src/netpulse/UploadPlanView.tsx`)

Two explicit upload modes:

- Raw mode
  - Upload workbook needing planning.
  - Calls `POST /api/upload`, then `POST /api/replan`.
  - Planned result workbook becomes active globally.

- Final mode
  - Upload already-planned workbook.
  - Calls `POST /api/upload_final`.
  - Workbook becomes active immediately, no replanning.

### 2) Planning (`src/netpulse/PlanningView.tsx`)

- Calls `GET /api/network`.
- Shows KPI summary and detailed hard/soft rule breakdown.
- Displays region cards and map layers for Regions/PCI/Mod4/Mod3/RSI.
- Rule summary modal describes all clash rule categories.

### 3) Clashes (`src/netpulse/ClashesView.tsx`)

- Calls `GET /api/network`, `GET /api/clash_info`.
- Interactive clash map with filters by region/type.
- Sector explainer is here (not in AI tab):
  - Searches sector ids
  - Calls `GET /api/explain/{sector_id}`
  - Shows hard/soft causes and neighbors behind each clash
- Per-sector clash info panel calls `GET /api/clash_info/{sector_id}`.

### 4) Assignments (`src/netpulse/AssignmentsView.tsx`)

- Calls `GET /api/sectors`.
- Shows sector table with sorting/filtering:
  - query, region, mod4, clash type, row limit
- CSV export of current filtered rows.

### 5) Add Site (`src/netpulse/AddSiteView.tsx`)

Two planning paths:

- Re-plan existing site
  - Preview: `POST /api/replan_site/preview`
  - Draft option refresh: `POST /api/replan_site/options`
  - Commit: `POST /api/replan_site/commit`
  - Existing-site preview is editable:
    - choose Mod4 first
    - choose Mod3 next
    - PCI dropdown updates to show only valid PCI values for that Mod4/Mod3 combination
  - Replan preview map keeps the original sector geometry so wedges render correctly while editing

- Add brand-new site
  - Pick lat/lon on map (click/drag), with 7km and 14km guide rings
  - Preview: `POST /api/addsite/new/preview`
  - Commit: `POST /api/addsite/new/commit`

New site id region prefixes (`ALX`, `SIN`, `UPP`, `DEL`) auto-center the picker map.

### 6) AI Agent (`src/netpulse/AssistantView.tsx`)

- Calls `GET /api/agent/tools`, `GET /api/agent/info`, `POST /api/agent/chat`.
- Tool-calling assistant UI:
  - Shows user/assistant chat
  - Shows each executed tool call and JSON result
- Current backend route behavior is Ollama-driven tool calling.

### 7) Voronoi Compare (`src/netpulse/VoronoiCompareView.tsx`)

Compares old vs current planning around a target site cluster.

- Loads current workbook via `GET /api/sectors_raw`.
- Old workbook upload supports both types:
  - tries raw upload first
  - falls back to final upload
- Two visual modes:
  - Diagram mode: Voronoi adjacency-based Mod4 border clashes
  - Real map mode: true wedge geometry on Leaflet basemap
- Unplanned sectors are skipped safely (no crash).

## Map implementation

Shared map component: `src/netpulse/MapView.tsx`.

- Leaflet basemap: CARTO `light_all` tiles
- No API key needed
- Sector wedge geometry from `geo.ts`
- Color/rule semantics from `colors.ts`
- Supports:
  - fit-to-sites and fly-to focus
  - site/sector selection
  - measurement circle overlays
  - pickable mode with draggable marker

## Frontend to backend contract

API wrapper file: `src/netpulse/api.ts`.

Key behaviors:

- Central request helper with error handling
- 404 stale workbook detection triggers `netpulse:workbook-missing`
- Strong types for network, sectors, replan editor options, tool-calls, and clash definitions
- Endpoint coverage includes upload/replan/add-site/assistant/voronoi paths

## Scripts

From `package.json`:

- `npm run dev` - run Vite dev server
- `npm run build` - production build
- `npm run preview` - preview built output
- `npm run format` - format via `oxfmt`

## Current integration assumptions

- Backend CORS allows all origins.
- Frontend assumes backend availability at `VITE_API_URL`.
- Workbook ids (`live:*`) are runtime-scoped and may expire after backend restart.
- NetPulse tabs require an active workbook; otherwise they show an upload prompt.

## Troubleshooting

- Empty or stale workbook behavior:
  - Re-upload workbook from Upload and Plan.
- API unreachable errors:
  - Check backend is running and `VITE_API_URL` is correct.
  - After backend API changes, restart the FastAPI server so new Add Site editor endpoints are available.
- Map tile issues:
  - Confirm internet access to CARTO/OpenStreetMap tile hosts.
- AI Agent unavailable:
  - Check backend agent configuration and Ollama runtime.
