"""
netfix-backend -- the orchestration layer that turns the platform's existing,
independently-working services (ran-cleaning-service, ran-anomaly-service,
KPI thresholding, rule-based cause matching, LLM explanation) into the
two-phase NetFix pipeline, built around one persistent Analysis Session.

This package does not reimplement cleaning, anomaly detection, or the LLM
call -- it wraps the already-verified services (see services/*.py for
exactly which module each wraps and why) behind a clean set of
single-responsibility classes, and adds the one thing that didn't exist
before: a Session object that Phase 1 and Phase 2 both read from and write
to, so re-running Phase 2 with new thresholds never re-triggers Phase 1's
expensive cleaning/anomaly-detection work.

See README.md for the full architecture explanation and how to run it via
the CLI or FastAPI.
"""

__version__ = "1.0.0"
