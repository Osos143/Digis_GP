"""
Turns the full reason-matching result JSON into clearly labelled, readable
text sections for the LLM prompt. The formatter deliberately presents the
data in a structured but natural way — NOT as raw JSON — so the LLM is
encouraged to interpret and explain rather than echo back field names.
"""

from __future__ import annotations

from typing import Any

from ran_rca_explanation.schema import ExplanationRequest


def build_prompt_context(request: ExplanationRequest) -> dict[str, str]:
    """Build prompt context sections from the full reason-matching result."""
    rca = request.rca_result_json

    # ── Diagnosis ───────────────────────────────────────────────────
    diagnosis = rca.get("diagnosis", {})
    diag_lines = []
    if diagnosis:
        if diagnosis.get("problem_name"):
            diag_lines.append(f"Identified Problem: {diagnosis['problem_name']}")
        if diagnosis.get("category"):
            diag_lines.append(f"Category: {diagnosis['category']}")
        if diagnosis.get("cause_id"):
            diag_lines.append(f"Matched Cause ID: {diagnosis['cause_id']}")
        if diagnosis.get("severity"):
            diag_lines.append(f"Severity Level: {diagnosis['severity']}")
        if diagnosis.get("reason"):
            diag_lines.append(f"Detailed Reason: {diagnosis['reason']}")
    diagnosis_text = "\n".join(diag_lines) if diag_lines else "(no diagnosis available)"

    # ── KPI Evidence (formatted as readable metrics) ────────────────
    kpi = rca.get("key_kpi_evidence", {})
    kpi_lines = []
    if kpi:
        # Group and format KPIs with human-readable labels
        label_map = {
            "rsrp": "RSRP (Reference Signal Received Power)",
            "sinr": "SINR (Signal-to-Interference-plus-Noise Ratio)",
            "rsrq": "RSRQ (Reference Signal Received Quality)",
            "bler": "BLER (Block Error Rate)",
            "actual_tp": "Actual Throughput",
            "expected_tp": "Expected Throughput",
            "tp_ratio": "Throughput Ratio (Actual/Expected)",
            "ta": "Timing Advance (distance indicator)",
            "cqi": "CQI (Channel Quality Indicator)",
            "ri": "RI (Rank Indicator)",
            "scell_rsrp": "SCell RSRP",
            "scell_sinr": "SCell SINR",
            "scell_cqi": "SCell CQI",
            "scell_bler_pct": "SCell BLER %",
            "pci": "PCI (Physical Cell ID)",
            "earfcn": "EARFCN (Carrier Frequency)",
            "band": "Band",
            "ca_active": "Carrier Aggregation Active",
            "severity": "Severity",
        }
        for k, v in kpi.items():
            if v is not None:
                label = label_map.get(k, k.replace("_", " ").title())
                if isinstance(v, bool):
                    v_str = "Yes" if v else "No"
                elif isinstance(v, float):
                    v_str = f"{v:.2f}"
                else:
                    v_str = str(v)

                # Add units where known
                unit = ""
                if k in ("rsrp", "scell_rsrp"):
                    unit = " dBm"
                elif k in ("sinr", "scell_sinr"):
                    unit = " dB"
                elif k in ("rsrq",):
                    unit = " dB"
                elif k in ("actual_tp", "expected_tp"):
                    unit = " Mbps"
                elif k in ("bler", "scell_bler_pct"):
                    unit = "%"

                kpi_lines.append(f"  {label}: {v_str}{unit}")
    kpi_text = "\n".join(kpi_lines) if kpi_lines else "(no KPI measurements available)"

    # ── Recommended Solutions & Standards ────────────────────────────
    rec = rca.get("recommended_solution", {})
    actions = rec.get("recommended_actions", []) if rec else []
    refs = rec.get("standards_and_vendor_references", []) if rec else []
    sol_lines = []
    if actions:
        for i, a in enumerate(actions, 1):
            sol_lines.append(f"  Action {i}: {a}")
    if refs:
        sol_lines.append("")
        sol_lines.append("  Relevant Standards & Vendor Guidelines:")
        for r in refs:
            if isinstance(r, dict):
                sol_lines.append(f"    - {r.get('source', 'Unknown')}: {r.get('note', '')}")
            else:
                sol_lines.append(f"    - {r}")
    solution_text = "\n".join(sol_lines) if sol_lines else "(no solutions provided)"

    # ── Supporting Evidence ──────────────────────────────────────────
    sup = rca.get("supporting_evidence", [])
    sup_lines = []
    if sup:
        for ev in sup:
            if isinstance(ev, dict):
                sup_lines.append(f"  - [{ev.get('id', '?')}] {ev.get('name', '?')}: {ev.get('reason', '')}")
            else:
                sup_lines.append(f"  - {ev}")
    supporting_text = "\n".join(sup_lines) if sup_lines else "(no additional supporting evidence)"

    return {
        "anomaly_id": request.anomaly_id,
        "diagnosis": diagnosis_text,
        "kpi_evidence": kpi_text,
        "solutions": solution_text,
        "supporting_evidence": supporting_text,
    }
