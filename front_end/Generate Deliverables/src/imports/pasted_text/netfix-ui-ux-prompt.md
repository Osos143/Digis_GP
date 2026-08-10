# NetFix -- Figma AI UI/UX Design Prompt
Design a complete professional **enterprise web application UI/UX** for
a telecom RAN optimization platform named **NetFix**.
The design should look like a modern telecom operations platform
inspired by **Nokia NetAct**, **Ericsson ENM**, **Grafana Enterprise**,
and modern SaaS dashboards. The interface should be clean, highly
organized, information-dense, and optimized for engineers who spend
hours analyzing network performance.
## Project Overview
NetFix is an AI-powered RAN (Radio Access Network) anomaly detection and
root cause analysis platform.
The platform enables RAN Optimization Engineers and Data Scientists to
upload Drive Test datasets, automatically detect anomalies, determine
possible root causes, recommend optimization actions, explain findings
using AI, visualize anomalies geographically, and generate technical
reports.
The interface should emphasize clarity, efficiency, and fast navigation
while maintaining a professional enterprise aesthetic.
## Users
### Primary Users
-   RAN Optimization Engineers
-   Data Scientists
### Secondary Users
-   System Administrators
## User Roles
### Engineer
-   Upload datasets
-   Configure analysis
-   View results
-   Explore anomaly details
-   View maps
-   Visualize statistics
-   Generate reports
-   Interact with AI assistant
### Admin
-   Manage users
-   Add/Delete users
-   Monitor all analysis sessions
-   View uploaded datasets
-   View generated reports
-   View session history
-   View engineer activities
## Engineer Workflow
Login → Dashboard → Upload Drive Test Dataset → Preview Dataset → Select
Features/KPIs → Configure thresholds (Poor, Acceptable, Good) → Run
Analysis → Analysis Progress → Results Dashboard → Select Anomaly →
Anomaly Details → AI Explanation → Root Causes → Optimization Actions →
Interactive Map → Statistics → Generate PDF Report
## Main Pages
-   Login
-   Dashboard
-   Upload Dataset
-   Dataset Preview
-   Analysis Configuration
-   Analysis Progress
-   Results Dashboard
-   Anomaly Details
-   Interactive Map
-   Statistics
-   Reports
-   Dataset History
-   Settings
-   Admin Dashboard
## Dashboard
Display: - Number of uploaded samples - Number of detected anomalies -
Percentage of anomalies - Most frequent anomaly - Most common root
cause - Analysis trend over time - Recent uploads - Recent reports
Charts: - Anomaly trend - KPI distribution - Root cause frequency -
Severity distribution - Network health score
Quick actions: - Upload Dataset - Run Analysis - Generate Report - Ask
AI
## Upload Dataset
Include: - Drag & Drop - Browse button - File preview - Supported
formats (CSV, Excel, Parquet) - Progress bar - Previous uploads -
Dataset summary
## Analysis Configuration
Allow selecting KPIs and editing three thresholds for each KPI: - Poor -
Acceptable - Good
Support enabling/disabling KPIs and configuring detection sensitivity.
## Results Dashboard
Include: - Search - Advanced filters - Interactive map - Charts -
Results table - Download/Export
Columns: - Anomaly - Severity - Confidence - Cell ID - Latitude -
Longitude - Time - Status
## Anomaly Details
Display: - Anomaly name - Severity - Confidence - Affected Cell -
Supporting KPIs - Threshold comparison table - Root causes -
Optimization recommendations - AI explanation - Timeline - KPI trend
charts - Export PDF
## Interactive Map
Use OpenStreetMap with: - Drive test route - Cell locations - Heatmap -
Anomaly markers - Coverage layer
Clicking a marker should show: - Anomaly summary - Cell ID - Severity -
KPIs - Timestamp - View Details button
## Statistics
Provide: - KPI trends - Histograms - Scatter plots - Heatmaps - Pie
charts - Time-series - Distribution plots - Correlation matrix - Root
cause statistics
## AI Assistant
Capabilities: - Explain anomalies - Compare anomalies - Recommend
optimization actions - Summarize datasets - Answer questions about
uploaded files - Generate reports
## Reports
Professional PDF containing: - Executive summary - Detected anomalies -
KPI evidence - Root causes - Recommendations - AI explanations -
Charts - Maps
## Visual Style
Inspired by Nokia NetAct.
### Color Palette
-   Primary: #1565C0
-   Secondary: #00ACC1
-   Success: #2E7D32
-   Warning: #F9A825
-   Critical: #D32F2F
-   Background: #F4F6F8
-   Surface: #FFFFFF
-   Text: #263238
-   Borders: #CFD8DC
### Typography
Use Inter, Roboto, or IBM Plex Sans.
### Navigation
Left sidebar: - Dashboard - Upload Dataset - History - Analysis -
Results - Map - Statistics - Reports - AI Assistant - Settings - Admin
Top bar: - Search - Notifications - Profile - Theme - Help
## UX Principles
Prioritize engineer productivity, minimize clicks, clearly visualize KPI
thresholds with color-coded badges, and present AI explanations
alongside engineering evidence.
## Deliverables
Generate: - High-fidelity desktop web UI (1440 px) - Design system -
Component library - Clickable prototype - Empty/loading/error states -
Interactive components - Enterprise-quality telecom dashboard