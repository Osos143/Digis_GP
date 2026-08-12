"""
ran-rca-explanation-service

A standalone service, independent of the rest of the ran-telco-platform
codebase (no imports from it, no shared dependencies beyond common
libraries). Its one job: given a JSON document describing a detected
anomaly -- its KPI/evidence data, its matched root-cause reason(s), and
(optionally) suggested solutions someone/something else has already
proposed -- generate a polished, professional, plain-language explanation
of that anomaly, written the way a senior RAN/RF optimization engineer
would explain it to a colleague or stakeholder.

This service does NOT detect anomalies, does NOT decide root causes, and
does NOT invent solutions. It only explains what it's given, grounded
strictly in the evidence in that JSON. See README.md for the full input
contract, the model choice and why, and how to run it via CLI or API.
"""

__version__ = "1.0.0"
