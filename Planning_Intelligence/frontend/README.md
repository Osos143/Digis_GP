# Frontend --- NetFix + NetPulse

The frontend is the web application layer of the NetFix AI / NetPulse 5G
planning platform.

It provides a single React application with two workspaces:

-   **Drive Test & Anomaly** --- the existing NetFix workspace.
-   **5G Network Planning / NetPulse** --- the NR5G PCI, Mod3, Mod4, RSI
    planning workspace.

The frontend does not perform the telecom planning algorithms itself. It
provides the user interface, visualization, workflow management, API
integration, and AI interaction layer. All planning and validation
decisions are returned by the backend deterministic engine.

------------------------------------------------------------------------

## 1. Frontend Architecture

``` text
                         ┌──────────────────────────┐
                         │          User            │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       React Frontend     │
                         │                          │
                         │  Login / Workspace       │
                         │  NetPulse Navigation     │
                         │  Maps / Tables / Charts   │
                         │  Planning Workflows      │
                         │  AI Assistant             │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       API Layer          │
                         │       src/netpulse/api.ts│
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       FastAPI Backend     │
                         │                          │
                         │  Planning Engine         │
                         │  Validator               │
                         │  Add Site / Replan       │
                         │  AI Tool Calling          │
                         └──────────────────────────┘
```

### Core frontend principle

The frontend is responsible for:

-   collecting user input;
-   calling the correct backend endpoint;
-   presenting backend results;
-   allowing engineers to inspect and edit planning results;
-   visualizing network geometry and clashes;
-   maintaining the active workbook/session state.

The frontend does **not** independently calculate PCI, Mod4, Mod3, RSI,
neighbor relationships, or engineering conflict decisions.

------------------------------------------------------------------------

# 2. Technology Stack

  Technology                 Purpose
  -------------------------- -------------------------------------------
  **React 19**               Component-based UI
  **TypeScript**             Type-safe frontend development
  **Vite**                   Development server and build tooling
  **Tailwind CSS v4**        UI styling
  **Leaflet**                Interactive network maps
  **React Leaflet**          React integration for Leaflet
  **Recharts**               Charts used by the application
  **Lucide React**           UI icons
  **XLSX**                   Client-side workbook/CSV-related handling
  **Browser localStorage**   Persist active NetPulse view/workbook

------------------------------------------------------------------------

# 3. Quick Start

## 3.1 Install dependencies

From the project root:

``` bash
cd frontend
npm install
```

## 3.2 Configure the backend URL

Copy the environment template:

``` bash
cp .env.example .env
```

Set:

``` env
VITE_API_URL=http://localhost:8000
```

On Windows PowerShell:

``` powershell
Copy-Item .env.example .env
```

Then edit `.env` if required.

## 3.3 Start the frontend

``` bash
npm run dev
```

Vite normally starts the frontend at:

``` text
http://localhost:5173
```

The exact URL is printed by Vite in the terminal.

------------------------------------------------------------------------

# 4. Frontend / Backend Communication

All NetPulse backend requests are centralized through the API helper
layer.

``` text
React View
    │
    ▼
src/netpulse/api.ts
    │
    ▼
VITE_API_URL
    │
    ▼
FastAPI /api/*
```

The frontend passes the active workbook ID to endpoints that require
network data.

Example:

``` text
GET /api/network?workbook=<id>
```

This keeps the individual React views focused on presentation and
workflow logic instead of duplicating HTTP configuration.

------------------------------------------------------------------------

# 5. Application Shell

The main application entry point is:

``` text
src/App.tsx
```

The application uses one React shell for both workspaces.

``` text
Login
 │
 ├── Drive Test & Anomaly
 │
 └── 5G Network Planning
          │
          └── NetPulse
```

The selected workspace is controlled from the application state.

The NetPulse workspace uses a `currentView` value to determine which
planning screen is rendered.

------------------------------------------------------------------------

# 6. Login and Workspace Selection

The login screen allows the user to choose between:

``` text
Drive Test & Anomaly
5G Network Planning
```

Selecting:

``` text
5G Network Planning
```

opens the NetPulse planning workspace.

The NetPulse sidebar provides navigation between planning views.

A:

``` text
Switch Workspace
```

action returns the user to the workspace selection/login screen.

------------------------------------------------------------------------

# 7. NetPulse Navigation

The current NetPulse workspace contains the following main views:

``` text
Upload & Plan
Planning
Clashes
Assignments
Add Site
AI Assistant
Voronoi Compare
```

The main routing/state mapping is handled in:

``` text
src/App.tsx
```

The planning views are located under:

``` text
src/netpulse/
```

------------------------------------------------------------------------

# 8. Runtime State Management

NetPulse stores important session state in browser `localStorage`.

Current keys include:

``` text
netpulse-current-view
netpulse-workbook
```

### `netpulse-current-view`

Stores the currently selected NetPulse screen.

### `netpulse-workbook`

Stores the active backend workbook ID.

This allows the frontend to preserve the selected workbook and current
view during normal page navigation or reloads.

------------------------------------------------------------------------

# 9. Stale / Missing Workbook Handling

Backend workbook IDs can become invalid if the corresponding file is
removed or the backend state is reset.

The frontend listens for:

``` text
netpulse:workbook-missing
```

When this happens, the application:

1.  clears the active workbook;
2.  resets the NetPulse state;
3.  redirects the user to:

``` text
Upload & Plan
```

This prevents the user from continuing to interact with a workbook that
no longer exists.

------------------------------------------------------------------------

# 10. Upload & Plan

Component:

``` text
src/netpulse/UploadPlanView.tsx
```

This is the entry point for network planning.

The UI intentionally provides two upload modes.

------------------------------------------------------------------------

## 10.1 Raw Workbook Mode

Used when the workbook requires planning.

Flow:

``` text
Select workbook
      ↓
POST /api/upload
      ↓
Receive workbook ID
      ↓
POST /api/replan?workbook=<id>
      ↓
Backend performs planning
      ↓
Receive planned workbook ID
      ↓
Set planned workbook as active
```

The resulting planned workbook becomes the global NetPulse workbook.

This allows the user to move directly into:

-   Planning;
-   Clashes;
-   Assignments;
-   Add Site;
-   AI Assistant;
-   Voronoi Compare.

------------------------------------------------------------------------

## 10.2 Final Workbook Mode

Used when the workbook is already planned.

Flow:

``` text
Select planned workbook
      ↓
POST /api/upload_final
      ↓
Backend validates existing assignments
      ↓
Workbook becomes active
```

No new planning pass is performed.

This prevents an already planned workbook from being unintentionally
overwritten.

------------------------------------------------------------------------

# 11. Planning Dashboard

Component:

``` text
src/netpulse/PlanningView.tsx
```

The Planning view provides the high-level network overview.

It calls:

``` text
GET /api/network
```

and presents the returned network/KPI information.

### Main capabilities

-   network KPI summary;
-   hard-rule results;
-   soft-rule results;
-   regional summaries;
-   planning status;
-   network map;
-   map layer switching;
-   rule explanation.

------------------------------------------------------------------------

# 12. KPI and Rule Summary

The Planning view presents the planning result in an engineer-friendly
dashboard.

It separates engineering rules into categories such as:

### Hard rules

Examples include:

-   PCI collision;
-   PCI confusion;
-   RSI validation;
-   Mod3 adjacent/site rules;
-   Mod4 intra-site rules.

### Soft rules

Examples include:

-   Mod3 non-adjacent reuse;
-   Mod4 inter-site reuse;
-   Mod4 non-adjacent intra-site reuse;
-   other optimization-level conflicts.

A rule summary modal provides additional descriptions of the clash
categories.

------------------------------------------------------------------------

# 13. Planning Map

The Planning view uses the shared map functionality to visualize the
network.

The user can switch between different visualization layers, including:

``` text
Regions
PCI
Mod4
Mod3
RSI
```

The map can display:

-   sites;
-   sector directions;
-   sector values;
-   regional grouping;
-   conflict information;
-   coverage-style geometry.

------------------------------------------------------------------------

# 14. Interactive Map Architecture

Map-related components/utilities include:

``` text
MapView.tsx
geo.ts
voronoi.ts
```

### `MapView.tsx`

Provides the reusable Leaflet-based network map.

### `geo.ts`

Contains frontend geographic/geometry helpers used for:

-   sector geometry;
-   distance-related visualization;
-   map positioning;
-   geographic calculations required by the UI.

### `voronoi.ts`

Contains the frontend logic used for Voronoi-style visualization and
comparison.

The frontend geometry is primarily for visualization and interaction. It
does not replace the backend planning/validation engine.

------------------------------------------------------------------------

# 15. Clashes Explorer

Component:

``` text
src/netpulse/ClashesView.tsx
```

The Clashes view is the main interactive conflict investigation screen.

It calls:

``` text
GET /api/network
GET /api/clash_info
```

and uses the returned network/clash data to build the UI.

------------------------------------------------------------------------

## 15.1 Clash Filtering

Users can filter clashes by:

-   region;
-   clash type;
-   sector/site context.

This makes it possible to investigate a large network without inspecting
every sector manually.

------------------------------------------------------------------------

## 15.2 Interactive Clash Map

The clash map visually highlights affected network areas.

The map can show:

-   sector/site locations;
-   sector geometry;
-   clash markers;
-   relevant network regions;
-   clash overlays.

The UI uses distinct visual treatment for important conflict categories.

------------------------------------------------------------------------

## 15.3 Sector Explainer

The Clashes page contains a dedicated sector explanation workflow.

The user can search for a sector ID.

The frontend calls:

``` text
GET /api/explain/{sector_id}
```

The response is used to display:

-   hard-rule causes;
-   soft-rule causes;
-   relevant neighbors;
-   engineering narration.

This explanation is deterministic and comes from the backend explanation
engine.

------------------------------------------------------------------------

## 15.4 Per-Sector Clash Information

The frontend can request:

``` text
GET /api/clash_info/{sector_id}
```

This provides:

-   static clash definitions;
-   sector-specific live conflict information.

This allows the UI to explain not only that a clash exists, but what the
clash category means and why that sector is affected.

------------------------------------------------------------------------

# 16. Assignments Explorer

Component:

``` text
src/netpulse/AssignmentsView.tsx
```

The Assignments view provides a detailed sector-level table.

It calls:

``` text
GET /api/sectors
```

The table is designed for detailed inspection rather than high-level
visualization.

------------------------------------------------------------------------

## 16.1 Assignment Fields

The view can expose sector information including:

``` text
Site
Sector
PCI
Mod3
Mod4
RSI
Region
Clash flags
Planning information
```

------------------------------------------------------------------------

## 16.2 Assignment Filters

The table supports filtering by:

-   search/query;
-   region;
-   Mod4;
-   clash type;
-   row limit.

This allows engineers to quickly isolate a subset of sectors.

Examples:

``` text
Show only ALX sectors
Show Mod4 = 2
Show sectors with conflicts
Search ALX001_2
```

------------------------------------------------------------------------

## 16.3 Sorting

The assignment table supports sorting so engineers can inspect the data
according to the currently important field.

------------------------------------------------------------------------

## 16.4 CSV Export

The current filtered assignment dataset can be exported as CSV.

The export reflects the user's active filtering rather than blindly
exporting the entire dataset.

------------------------------------------------------------------------

# 17. Add Site Workflow

Component:

``` text
src/netpulse/AddSiteView.tsx
```

The Add Site screen contains two related workflows:

``` text
Replan Existing Site
Add Brand-New Site
```

This allows the same frontend workflow to support both network expansion
and controlled site replanning.

------------------------------------------------------------------------

# 18. Replan Existing Site

The existing-site workflow is designed to modify one target site while
preserving the rest of the network.

### Preview

``` http
POST /api/replan_site/preview
```

The frontend sends:

``` text
workbook
target_site
```

The backend returns:

-   previous assignment values;
-   new proposed assignments;
-   neighboring sectors;
-   editor options.

------------------------------------------------------------------------

# 19. Guided Replan Editor

The existing-site replan UI is interactive.

The user can work through:

``` text
Mod4
  ↓
Mod3
  ↓
PCI
```

### Mod4 selection

The user selects a valid Mod4 value.

### Mod3 selection

The user selects a valid Mod3 value.

### PCI selection

The PCI options are dynamically restricted according to the current
Mod4/Mod3 choices.

This means the frontend does not present an unrestricted PCI list. It
uses the deterministic backend-generated valid candidates.

------------------------------------------------------------------------

# 20. Dynamic Replan Options

As the user changes the current draft, the frontend calls:

``` http
POST /api/replan_site/options
```

with the current:

``` text
assignments
mod3_choices
```

The backend recomputes the editor options.

The frontend then refreshes the available choices.

This creates a guided planning editor where the user cannot simply
select arbitrary combinations without seeing the backend's current legal
options.

------------------------------------------------------------------------

# 21. Replan Preview Map

During an existing-site replan, the map preserves the original sector
geometry.

This is important because changing PCI/Mod3/Mod4 should not visually
change the physical sector orientation.

The preview therefore keeps:

-   site coordinates;
-   sector azimuth;
-   sector wedge geometry.

Only the planning attributes are changed in the draft.

------------------------------------------------------------------------

# 22. Commit Existing-Site Replan

After the user is satisfied with the draft:

``` http
POST /api/replan_site/commit
```

The frontend submits the final assignments.

The backend:

``` text
loads base workbook
      ↓
applies target-site changes
      ↓
preserves required existing RSI values
      ↓
validates
      ↓
exports
      ↓
creates new live workbook
```

The returned workbook becomes the active NetPulse workbook.

------------------------------------------------------------------------

# 23. Add Brand-New Site

The same Add Site screen supports creation of a completely new site.

The user can:

-   enter a site ID;
-   select a location;
-   configure sector azimuths;
-   preview the assignment;
-   inspect neighboring sectors;
-   commit the new site.

------------------------------------------------------------------------

# 24. New-Site Map Picker

The map picker allows the engineer to select the new site's location.

The location can be selected by:

-   clicking on the map;
-   dragging the site marker.

The UI also displays planning guide rings:

``` text
7 km
14 km
```

These provide visual context for the Tier-1 and Tier-2 planning regions.

The rings are visualization aids and correspond to the backend
neighbor/planning distances.

------------------------------------------------------------------------

# 25. Region-Aware New-Site Map

New site IDs use known region prefixes:

``` text
ALX
SIN
UPP
DEL
```

The frontend automatically uses the prefix to choose an appropriate
initial map center for the site picker.

This improves the workflow by avoiding a blank/global map when starting
a new site.

------------------------------------------------------------------------

# 26. New-Site Preview

The frontend calls:

``` http
POST /api/addsite/new/preview
```

with:

``` text
site_id
latitude
longitude
azimuths
```

The backend returns:

``` text
assignments
neighbors
temporary workbook id
```

The UI can then show:

-   proposed PCI;
-   proposed Mod4;
-   proposed RSI;
-   neighboring sectors;
-   neighbor assignments;
-   map context.

------------------------------------------------------------------------

# 27. New-Site Commit

After reviewing the preview:

``` http
POST /api/addsite/new/commit
```

The frontend sends the temporary planning result.

The backend validates and exports the final workbook.

The returned workbook becomes the new active NetPulse workbook.

Existing network assignments are preserved.

------------------------------------------------------------------------

# 28. AI Assistant

Component:

``` text
src/netpulse/AssistantView.tsx
```

The AI Assistant provides a natural-language interface to the
deterministic planning tools.

The frontend communicates with:

``` text
GET /api/agent/tools
GET /api/agent/info
POST /api/agent/chat
```

------------------------------------------------------------------------

# 29. AI Assistant Responsibilities

The frontend AI experience allows an engineer to ask questions about the
active network.

Examples:

``` text
Why is this sector causing a clash?

Why can't this sector use this PCI?

Show me the neighbors of this sector.

Which sectors have high conflict levels?

Explain this planning result.

What happens if I add a site here?
```

The AI assistant is not the source of the planning result.

The backend tool-calling agent selects and executes deterministic tools,
then returns the result for the AI to explain.

------------------------------------------------------------------------

# 30. Tool-Calling Transparency

The Assistant UI does not only display the final natural-language
answer.

It can also show:

``` text
Tool name
Tool input
Tool result / JSON
```

This provides visibility into what the agent actually executed.

Example:

``` text
User question
     ↓
AI selects tool
     ↓
Tool input
     ↓
Deterministic result
     ↓
AI explanation
```

This is especially useful for debugging, demonstrations, and engineering
trust.

------------------------------------------------------------------------

# 31. AI Model Information

The frontend calls:

``` text
GET /api/agent/info
```

to obtain the backend's active model information.

The UI can display the model reported by the backend instead of assuming
a hard-coded model name.

This keeps the displayed model synchronized with the actual Ollama
configuration.

------------------------------------------------------------------------

# 32. Multi-Turn AI Conversation

The assistant sends conversation history to:

``` http
POST /api/agent/chat
```

The request includes:

``` text
workbook
message
model
history
```

The history contains previous:

``` json
{
  "role": "user",
  "content": "..."
}
```

and:

``` json
{
  "role": "assistant",
  "content": "..."
}
```

messages.

This allows follow-up questions to remain contextual.

------------------------------------------------------------------------

# 33. Voronoi Compare

Component:

``` text
src/netpulse/VoronoiCompareView.tsx
```

The Voronoi Compare view is designed to compare network planning around
a target site/cluster.

It uses:

``` http
GET /api/sectors_raw
```

rather than the fully validated `/api/sectors` endpoint.

This is intentional because comparison can involve:

-   partially planned workbooks;
-   raw workbook data;
-   workbooks with missing PCI/RSI/Mod4 values.

------------------------------------------------------------------------

# 34. Old vs. Current Planning Comparison

The comparison workflow can be used to visualize changes between:

``` text
Old / previous planning
          ↓
       changes
          ↓
Current / optimized planning
```

The visualization focuses on the spatial impact around the selected
target area.

Typical comparison information includes:

-   site positions;
-   sector geometry;
-   planning values;
-   coverage-style regions;
-   changes between old and new states.

------------------------------------------------------------------------

# 35. Coverage Visualization

The frontend supports a Voronoi-style visualization to provide an
intuitive representation of spatial ownership.

Conceptually:

``` text
Sites
  ↓
Voronoi regions
  ↓
Approximate spatial ownership
```

This is useful for comparing the spatial distribution of the network
before and after planning changes.

It should be understood as a visualization/analysis aid rather than a
radio-propagation simulator.

------------------------------------------------------------------------

# 36. Map Geometry

Sector visualization is based on:

``` text
Latitude
Longitude
Azimuth
Cell radius / display radius
```

A sector is represented visually as a directional wedge around the site.

This makes the network map easier to understand than displaying sites as
simple points.

The geometry is especially useful for:

-   clash inspection;
-   new-site planning;
-   existing-site replanning;
-   coverage visualization;
-   before/after comparison.

------------------------------------------------------------------------

# 37. Reusable UI Components

The frontend uses reusable UI patterns/components for:

-   feature cards;
-   KPI cards;
-   panels;
-   maps;
-   badges;
-   filters;
-   modals;
-   tables;
-   status indicators;
-   loading states;
-   empty states;
-   error states.

The goal is to keep NetPulse views visually consistent while allowing
each screen to focus on its specific planning workflow.

------------------------------------------------------------------------

# 38. Frontend Folder Structure

The relevant frontend structure is:

``` text
frontend/
│
├── src/
│   ├── App.tsx
│   ├── vite-env.d.ts
│   │
│   └── netpulse/
│       ├── UploadPlanView.tsx
│       ├── PlanningView.tsx
│       ├── ClashesView.tsx
│       ├── AssignmentsView.tsx
│       ├── AddSiteView.tsx
│       ├── AssistantView.tsx
│       ├── VoronoiCompareView.tsx
│       ├── MapView.tsx
│       ├── geo.ts
│       ├── voronoi.ts
│       └── api.ts
│
├── public/
├── package.json
├── vite.config.*
├── tsconfig.*
├── .env.example
└── README.md
```

------------------------------------------------------------------------

# 39. Component Responsibilities

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  `App.tsx`                           Application shell, workspace
                                      selection, NetPulse view
                                      routing/state

  `UploadPlanView.tsx`                Raw/final workbook upload and
                                      planning

  `PlanningView.tsx`                  Network dashboard, KPIs, rule
                                      summaries and planning map

  `ClashesView.tsx`                   Clash filtering, map exploration
                                      and sector explanations

  `AssignmentsView.tsx`               Detailed sector assignment table,
                                      filters and CSV export

  `AddSiteView.tsx`                   New-site planning and existing-site
                                      replanning

  `AssistantView.tsx`                 AI tool-calling chat and tool trace

  `VoronoiCompareView.tsx`            Old/current planning spatial
                                      comparison

  `MapView.tsx`                       Shared interactive Leaflet map

  `geo.ts`                            Geographic and sector geometry
                                      helpers

  `voronoi.ts`                        Voronoi-style visualization helpers

  `api.ts`                            Centralized backend API
                                      communication
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 40. Frontend Data Flow

## Upload

``` text
User selects Excel file
        ↓
UploadPlanView
        ↓
api.ts
        ↓
POST /api/upload
        ↓
Backend
        ↓
Workbook ID
        ↓
React state + localStorage
```

## Planning

``` text
Active workbook
        ↓
PlanningView
        ↓
GET /api/network
        ↓
Network JSON + KPIs
        ↓
Dashboard + Map
```

## Clash Investigation

``` text
ClashesView
        ↓
GET /api/clash_info
GET /api/explain/{sector_id}
        ↓
Deterministic explanation
        ↓
Sector details + map
```

## Assignment Analysis

``` text
AssignmentsView
        ↓
GET /api/sectors
        ↓
Flat sector dataset
        ↓
Filters / sorting / CSV
```

## AI Assistant

``` text
AssistantView
        ↓
POST /api/agent/chat
        ↓
Tool-calling backend
        ↓
tool_calls + reply
        ↓
Chat + trace UI
```

------------------------------------------------------------------------

# 41. Active Workbook Lifecycle

The frontend treats the backend workbook ID as the active network
context.

``` text
Upload
   ↓
Workbook ID
   ↓
Set active workbook
   ↓
Planning / Clashes / Assignments
   ↓
Add Site or Replan
   ↓
New workbook ID
   ↓
Replace active workbook
```

Whenever a planning workflow creates a new live workbook, the frontend
switches to that new workbook for subsequent requests.

This prevents the UI from continuing to display stale planning data.

------------------------------------------------------------------------

# 42. API Endpoints Used by the Frontend

## Workbook

``` text
GET  /api/workbooks
POST /api/upload
POST /api/upload_final
GET  /api/download?workbook=<id>
```

## Planning

``` text
POST /api/replan?workbook=<id>
GET  /api/network?workbook=<id>
GET  /api/raw?workbook=<id>
GET  /api/sectors?workbook=<id>
GET  /api/sectors_raw?workbook=<id>
```

## Explanation

``` text
GET  /api/explain/{sector_id}?workbook=<id>
POST /api/chat
```

## Clash information

``` text
GET /api/clash_info
GET /api/clash_info/{sector_id}?workbook=<id>
```

## AI Agent

``` text
GET  /api/agent/tools
GET  /api/agent/info
POST /api/agent/chat
```

## New Site

``` text
POST /api/addsite/new/preview?workbook=<id>
POST /api/addsite/new/commit
```

## Existing Site Replanning

``` text
POST /api/replan_site/preview
POST /api/replan_site/options
POST /api/replan_site/commit
```

------------------------------------------------------------------------

# 43. Typical User Workflow

A normal planning session looks like:

``` text
1. Open application
        ↓
2. Select "5G Network Planning"
        ↓
3. Upload workbook
        ↓
4. Choose:
      Raw
      or
      Already Planned
        ↓
5. Run / load planning
        ↓
6. Review Planning dashboard
        ↓
7. Inspect map and KPIs
        ↓
8. Open Clashes
        ↓
9. Investigate problematic sectors
        ↓
10. Inspect Assignments
        ↓
11. Add a new site or replan an existing site if required
        ↓
12. Compare old/current planning
        ↓
13. Ask the AI Assistant for explanations
        ↓
14. Continue working with the new active workbook
```

------------------------------------------------------------------------

# 44. Engineering Visualization Philosophy

The frontend is designed to answer three questions visually:

### Where?

Map and geographic context.

### What?

PCI / Mod3 / Mod4 / RSI and clash status.

### Why?

Sector explanations, neighbor information, and AI-assisted
interpretation.

This is why the application combines:

``` text
Map
+
KPI dashboard
+
Clash explorer
+
Assignment table
+
AI assistant
```

rather than presenting the planning output only as an Excel file.

------------------------------------------------------------------------

# 45. Hard Rules vs. Soft Rules in the UI

The frontend distinguishes between rules that determine validity and
rules that represent optimization quality.

### Hard-rule information

Used to indicate serious planning violations such as:

``` text
PCI Collision
PCI Confusion
Mod3 violations
other validator-enforced constraints
```

### Soft-rule information

Used to indicate optimization pressure such as:

``` text
Mod4 inter-site reuse
Mod4 non-adjacent reuse
Mod3 non-adjacent reuse
RSI reuse pressure
```

This distinction helps the engineer understand whether a result is:

``` text
invalid
```

or:

``` text
valid but still improvable
```

------------------------------------------------------------------------

# 46. Frontend Does Not Reimplement Planning Logic

A critical architectural rule is:

``` text
Frontend ≠ Planning Engine
```

The frontend should not independently implement:

-   PCI candidate legality;
-   Mod4 optimization;
-   Mod3 engineering rules;
-   RSI conflict scoring;
-   Tier-1/Tier-2 neighbor generation;
-   clash validation.

Instead:

``` text
Frontend
   ↓
Backend API
   ↓
Deterministic planning engine
   ↓
Validated result
```

This prevents different engineering rules from appearing in different
parts of the application.

------------------------------------------------------------------------

# 47. Error and Loading States

The frontend handles common asynchronous states such as:

``` text
Loading
Success
Empty result
Backend error
Invalid workbook
Missing workbook
Planning in progress
Preview in progress
Commit in progress
```

For example, if a workbook is no longer available, the frontend does not
leave the user on a broken planning screen. It resets the workbook and
returns to Upload & Plan.

------------------------------------------------------------------------

# 48. Local Development

Start the backend first:

``` bash
uvicorn main:app --reload --port 8000
```

Then start the frontend:

``` bash
cd frontend
npm run dev
```

Verify the backend:

``` text
http://localhost:8000/api/health
```

Open the API documentation:

``` text
http://localhost:8000/docs
```

Open the frontend using the Vite URL printed in the terminal.

------------------------------------------------------------------------

# 49. Build for Production

Create a production frontend build:

``` bash
npm run build
```

Preview the production build locally:

``` bash
npm run preview
```

The generated production files are placed in the Vite build output
directory.

------------------------------------------------------------------------

# 50. Troubleshooting

## Backend connection error

Check:

``` env
VITE_API_URL=http://localhost:8000
```

and verify:

``` text
http://localhost:8000/api/health
```

is available.

------------------------------------------------------------------------

## Workbook no longer available

If the frontend resets to Upload & Plan, the backend workbook ID is no
longer valid.

Solution:

``` text
Upload the workbook again
```

and continue with the new workbook ID.

------------------------------------------------------------------------

## Raw workbook uploaded as final

If a workbook does not contain complete assignments, use:

``` text
Raw
```

mode.

------------------------------------------------------------------------

## Already planned workbook uploaded as raw

If the backend rejects a raw upload because it is already fully planned,
use:

``` text
Final
```

mode.

------------------------------------------------------------------------

## AI Assistant cannot connect

Check that the backend and Ollama service are running and that the
backend's configured:

``` text
OLLAMA_URL
OLLAMA_MODEL
```

are correct.

The frontend itself does not communicate directly with Ollama; it
communicates with the backend agent endpoint.

------------------------------------------------------------------------

# 51. Design Principles

### 1. Backend is the engineering source of truth

The frontend displays deterministic backend results.

### 2. Components own UI workflows

Each major planning workflow has its own React view.

### 3. API access is centralized

Backend communication should go through the API layer.

### 4. Workbook context is global

All NetPulse views operate on the active workbook.

### 5. Incremental planning preserves existing data

Add-site and replan workflows should not unexpectedly modify unrelated
sectors.

### 6. Visualization should explain, not decide

Maps and charts help engineers understand the plan but do not replace
deterministic validation.

### 7. AI should explain engineering results

The AI Assistant provides a natural-language interface to the planning
tools rather than becoming a second planning engine.

------------------------------------------------------------------------

# 52. Frontend Role in the Complete System

``` text
                    RF Engineer
                         │
                         ▼
              ┌─────────────────────┐
              │   React Frontend    │
              │                     │
              │ Upload              │
              │ Planning Dashboard  │
              │ Interactive Map     │
              │ Clash Explorer      │
              │ Assignment Table    │
              │ Add / Replan Site   │
              │ Voronoi Compare     │
              │ AI Assistant        │
              └──────────┬──────────┘
                         │
                         ▼
                   FastAPI API
                         │
                         ▼
              Deterministic Engine
                         │
                         ▼
               Validated Network Plan
```

------------------------------------------------------------------------

# 53. Final Frontend Concept

The NetPulse frontend turns the deterministic planning engine into an
interactive engineering workspace.

``` text
Upload
  ↓
Plan
  ↓
Visualize
  ↓
Validate
  ↓
Investigate
  ↓
Edit / Expand
  ↓
Compare
  ↓
Ask AI
```

### In one sentence

> **The frontend is the engineer's control center for uploading,
> planning, visualizing, validating, investigating, editing, comparing,
> and explaining an NR5G network plan --- while all engineering
> decisions remain in the deterministic backend.**
