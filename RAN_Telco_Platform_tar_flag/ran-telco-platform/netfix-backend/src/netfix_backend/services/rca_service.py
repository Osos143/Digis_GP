"""RCA classification service for analyzing anomaly incidents, storing outputs in MongoDB and Redis."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from pymongo import MongoClient
import redis

DEFAULT_MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
DEFAULT_MONGO_DB = os.environ.get("MONGO_DB", "ran_telco")
DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

RCA_DEMO_DIR = Path(os.environ.get("RCA_DEMO_DIR", "/opt/ran-telco/RCA_Demo"))
if not RCA_DEMO_DIR.exists():
    RCA_DEMO_DIR = Path("/media/mogahed/New Volume/iti_gp/Sakr_200/RCA_Demo")


def g(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur = d
    for p in path.split('.'):
        if cur is None or not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def num(x: Any) -> bool:
    return isinstance(x, (int, float))


def evaluate_condition(cond: Dict[str, Any], f: Dict[str, Any]) -> bool:
    if cond.get('not_computable'):
        return False
    if 'all' in cond:
        return all(evaluate_condition(c, f) for c in cond['all'])
    if 'any' in cond:
        return any(evaluate_condition(c, f) for c in cond['any'])
    if 'not' in cond:
        return not evaluate_condition(cond['not'], f)
    field, op, value = cond['field'], cond['op'], cond['value']
    fv = f.get(field)
    if fv is None:
        return False
    if op == '==':
        return fv == value
    if op == '!=':
        return fv != value
    if op == '<':
        return fv < value
    if op == '<=':
        return fv <= value
    if op == '>':
        return fv > value
    if op == '>=':
        return fv >= value
    if op == 'in':
        return fv in value
    raise ValueError(f"unknown operator {op}")


def evaluate_gate(rule: Dict[str, Any], f: Dict[str, Any]) -> bool:
    conds = rule['gate_conditions']
    logic = rule.get('gate_logic', 'ALL')
    if logic == 'ALL':
        return all(evaluate_condition(c, f) for c in conds)
    return any(evaluate_condition(c, f) for c in conds)


def evaluate_supporting_evidence(rule: Dict[str, Any], f: Dict[str, Any]) -> List[str]:
    return [ev['id'] for ev in rule.get('supporting_evidence', []) if evaluate_condition(ev['detection_conditions'], f)]


def extract_features(rec: Dict[str, Any]) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    f['rsrp'] = g(rec, 'radio_kpis.rsrp_median_dbm', g(rec, 'lte_rsrp', -98.0))
    f['rsrq'] = g(rec, 'radio_kpis.rsrq_median_db', g(rec, 'lte_rsrq', -10.0))
    f['sinr'] = g(rec, 'radio_kpis.sinr_median_db', g(rec, 'lte_sinr', 12.0))
    f['cqi'] = g(rec, 'radio_kpis.cqi_median', g(rec, 'lte_cqi', 8.0))
    f['mcs'] = g(rec, 'radio_kpis.mcs_median', g(rec, 'lte_mcs', 10.0))
    f['bler'] = g(rec, 'radio_kpis.bler_median_pct', g(rec, 'lte_bler', 5.0))
    f['rb_usage'] = g(rec, 'resource_kpis.rb_usage_median', g(rec, 'rb_usage', 50.0))
    f['tp_per_rb'] = g(rec, 'resource_kpis.throughput_per_rb_median', 0.5)
    f['rb_med_high'] = g(rec, 'resource_kpis.rb_medium_or_high_usage', True)
    f['actual_tp'] = g(rec, 'throughput.actual_median_mbps', g(rec, 'actual_lte_dl_throughput', g(rec, 'actual_tp', 18.5)))
    f['expected_tp'] = g(rec, 'throughput.expected_median_mbps', g(rec, 'expected_tp_ml_hgb_temporal_q50', g(rec, 'expected_tp_p75', 22.0)))
    f['ca_active'] = g(rec, 'ca_context.ca_active', False)
    f['carrier_count'] = g(rec, 'ca_context.carrier_count_median', 1.0)
    f['scell_rsrp'] = g(rec, 'ca_context.scell1_rsrp_median_dbm')
    f['scell_sinr'] = g(rec, 'ca_context.scell1_sinr_median_db')
    f['scell_cqi'] = g(rec, 'ca_context.scell1_cqi_median')
    f['scell_bler'] = g(rec, 'ca_context.scell1_bler_median_pct')
    f['temporal_drop'] = g(rec, 'statistical_evidence.temporal_drop', False)
    f['sustained_window'] = g(rec, 'statistical_evidence.sustained_window', False)
    f['low_tail_consensus'] = g(rec, 'statistical_evidence.low_tail_consensus', False)
    f['detection_case'] = rec.get('detection_case')
    f['severity'] = rec.get('severity', 'Medium')
    f['cell_prb_util'] = g(rec, 'rca_required_kpis.cell_prb_utilization_pct', 45.0)
    f['near_ho'] = bool(g(rec, 'rca_required_kpis.near_handover_mobility_flag', False))
    f['near_rach_fail'] = bool(g(rec, 'rca_required_kpis.near_rach_failure_flag', False))
    f['neighbor_avail'] = g(rec, 'rca_required_kpis.neighbor_cell_availability', 100.0)
    f['rank'] = g(rec, 'rca_required_kpis.lte_rank', 1.0)
    f['ue_speed'] = g(rec, 'rca_required_kpis.ue_speed_kmh', 0.0)
    f['gap_rsrp'] = g(rec, 'rca_required_kpis.serving_minus_best_neighbor_rsrp', 5.0)
    f['ho_count_pm5s'] = g(rec, 'rca_required_kpis.handover_mobility_count_pm5s', 0.0)
    f['ho_dwell'] = g(rec, 'rca_required_kpis.ho_dwell_time_s', 30.0)
    f['cell_median_tp'] = g(rec, 'cell_performance_context.cell_median_tp_mbps')
    f['cell_bad_rank'] = g(rec, 'cell_performance_context.cell_bad_rank', False)

    rach_reason = g(rec, 'rca_required_kpis.rach_reason', [])
    f['rlf_present'] = isinstance(rach_reason, list) and 'Radio link Failure' in rach_reason

    f['demand_confirmed'] = (f['detection_case'] == 'rb_conditioned_expected_underperformance') or bool(f['rb_med_high'])
    f['demand_confirmed_broad'] = num(f['expected_tp']) and f['expected_tp'] > 0.1
    f['bad_session'] = bool(f['sustained_window']) and bool(f['low_tail_consensus'])
    f['fallback'] = True

    f['underperform_80pct'] = num(f['expected_tp']) and num(f['actual_tp']) and f['actual_tp'] < 0.8 * f['expected_tp']
    own_radio_bad = (num(f['rsrp']) and f['rsrp'] < -110) or (num(f['sinr']) and f['sinr'] < 0)
    f['own_radio_normal'] = (num(f['rsrp']) and f['rsrp'] >= -110) and (num(f['sinr']) and f['sinr'] >= 0) and not own_radio_bad
    f['mimo_pattern'] = num(f['sinr']) and f['sinr'] >= 15 and num(f['rank']) and f['rank'] == 1
    f['not_mobility'] = not f['near_ho']
    f['not_mimo'] = not f['mimo_pattern']
    f['near_zero_tp'] = num(f['actual_tp']) and f['actual_tp'] < 0.05
    f['session_collapse'] = bool(f['temporal_drop']) and bool(f['bad_session'])
    f['cell_prb_util_spike'] = num(f['cell_prb_util']) and f['cell_prb_util'] >= 80
    f['neighbor_avail_drop'] = num(f['neighbor_avail']) and f['neighbor_avail'] < 80
    return f


def evaluate_priority_1_to_4(f: Dict[str, Any], kpi_rules: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    for rule in kpi_rules.get('rules', []):
        if not (1 <= rule['priority'] <= 4):
            continue
        if not evaluate_gate(rule, f):
            continue
        if 'alternatives' in rule:
            for alt in rule['alternatives']:
                if all(evaluate_condition(c, f) for c in alt['gate_conditions']):
                    return alt['id'], evaluate_supporting_evidence(rule, f)
            continue
        return rule['parent_id'], evaluate_supporting_evidence(rule, f)
    return None, []


def evaluate_priority_5_to_6(f: Dict[str, Any], kpi_rules: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    for rule in kpi_rules.get('rules', []):
        if not (5 <= rule['priority'] <= 6):
            continue
        if evaluate_gate(rule, f):
            return rule['parent_id'], evaluate_supporting_evidence(rule, f)
    return None, []


def evaluate_fallback(f: Dict[str, Any], kpi_rules: Dict[str, Any]) -> str:
    for rule in kpi_rules.get('rules', []):
        if rule['priority'] == 7 and rule['parent_id'] == 'C14' and evaluate_gate(rule, f):
            return 'C14'
    return 'C15'


def build_reason(cid: str, f: Dict[str, Any], id_to_cause: Dict[str, Dict[str, Any]]) -> str:
    cause = id_to_cause.get(cid, {})
    tmpl = cause.get('reason_template', f"Incident classified under cause ID {cid}.")
    vals = {
        'lte_rsrp': f.get('rsrp'),
        'lte_rsrq': f.get('rsrq'),
        'lte_sinr': f.get('sinr'),
        'lte_cqi': f.get('cqi'),
        'lte_mcs': f.get('mcs'),
        'lte_bler': f.get('bler'),
        'rb_utilization_pct': f.get('rb_usage'),
        'carrier_count': f.get('carrier_count'),
        'cell_prb_utilization_pct': f.get('cell_prb_util'),
        'throughput_gap_p75': (round(f['expected_tp'] - f['actual_tp'], 2) if num(f.get('expected_tp')) and num(f.get('actual_tp')) else None),
        'scell_rsrp': f.get('scell_rsrp'),
        'scell_sinr': f.get('scell_sinr'),
        'scell_cqi': f.get('scell_cqi'),
        'scell_bler': f.get('scell_bler'),
        'neighbor_cell_availability': f.get('neighbor_avail'),
        'handover_count': f.get('ho_count_pm5s'),
        'ue_speed_kmh': f.get('ue_speed'),
        'avg_rank': f.get('rank'),
        'dl_bandwidth_mhz': None,
        'dl_mcs': f.get('mcs'),
        'scell_rb_count': None,
    }

    def fmt(v: Any) -> Any:
        return round(v, 2) if isinstance(v, float) else v

    present = {k: fmt(v) for k, v in vals.items() if v is not None}
    missing = {k: 'n/a' for k, v in vals.items() if v is None}
    try:
        return tmpl.format(**present, **missing)
    except Exception:
        return tmpl


def build_supporting_evidence(matched_ids: List[str], f: Dict[str, Any], id_to_cause: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for eid in matched_ids:
        cause = id_to_cause.get(eid)
        if not cause:
            continue
        out.append({"id": eid, "name": cause['name'], "reason": build_reason(eid, f, id_to_cause)})
    return out


def build_solution(parent_id: str, matched_evidence: List[str], solutions: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, str]]]:
    sol = solutions.get(parent_id, {"recommended_actions": [], "standards_and_vendor_references": []})
    matched = set(matched_evidence + [parent_id])
    actions = [a['action'] for a in sol.get('recommended_actions', []) if a.get('applies_if') is None or a.get('applies_if') in matched]
    refs = [{"source": r['source'], "note": r['note']} for r in sol.get('standards_and_vendor_references', [])]
    return actions, refs


def build_lookup_maps(causes: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    id_to_cause: Dict[str, Dict[str, Any]] = {}
    id_to_subcat: Dict[str, Dict[str, Any]] = {}
    for cat in causes.get('priority_categories', []):
        for sc in cat.get('subcategories', []):
            for c in sc.get('causes_list', []):
                id_to_cause[c['id']] = c
                id_to_subcat[c['id']] = {
                    'category': cat['category'],
                    'subcategory': sc['subcategory'],
                    'parent_id': sc['parent_id'],
                }
    return id_to_cause, id_to_subcat


class RCAService:
    """Service to load RCA rules, analyze anomaly documents, write to MongoDB and Redis."""

    def __init__(self, mongo_uri: str = DEFAULT_MONGO_URI, mongo_db: str = DEFAULT_MONGO_DB, redis_url: str = DEFAULT_REDIS_URL):
        self.mongo_uri = mongo_uri
        self.mongo_db_name = mongo_db
        self.redis_url = redis_url
        self._causes: Optional[Dict[str, Any]] = None
        self._kpi_rules: Optional[Dict[str, Any]] = None
        self._solutions: Optional[Dict[str, Dict[str, Any]]] = None
        self._load_rule_files()

    def _load_rule_files(self) -> None:
        causes_path = RCA_DEMO_DIR / "causes (1).json"
        kpi_rules_path = RCA_DEMO_DIR / "kpi_rules (1).json"
        solutions_path = RCA_DEMO_DIR / "solutions.json"

        if not causes_path.exists():
            causes_path = RCA_DEMO_DIR / "causes.json"
        if not kpi_rules_path.exists():
            kpi_rules_path = RCA_DEMO_DIR / "kpi_rules.json"

        if causes_path.exists():
            self._causes = json.loads(causes_path.read_text(encoding="utf-8"))
        if kpi_rules_path.exists():
            self._kpi_rules = json.loads(kpi_rules_path.read_text(encoding="utf-8"))
        if solutions_path.exists():
            sol_doc = json.loads(solutions_path.read_text(encoding="utf-8"))
            if isinstance(sol_doc, dict) and 'solutions' in sol_doc:
                self._solutions = {s['id']: s for s in sol_doc['solutions']}
            elif isinstance(sol_doc, list):
                self._solutions = {s['id']: s for s in sol_doc}

    def get_redis_client(self) -> Optional[redis.Redis]:
        try:
            return redis.from_url(self.redis_url, socket_timeout=2)
        except Exception:
            return None

    def get_mongo_client(self) -> Optional[MongoClient]:
        try:
            client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=2000)
            return client
        except Exception:
            return None

    def cache_session_anomaly_ids(self, session_id: str, anomaly_docs: List[Dict[str, Any]]) -> List[str]:
        """Cache all anomaly IDs for a session/file into Redis and MongoDB."""
        ids = []
        for idx, a in enumerate(anomaly_docs):
            aid = a.get("incident_id") or a.get("id") or f"INC-{idx+1:06d}"
            if aid not in ids:
                ids.append(aid)

        if not ids:
            ids = [f"INC-{i:06d}" for i in range(1, 11)]

        redis_client = self.get_redis_client()
        if redis_client:
            try:
                cache_key = f"rca:session:{session_id}:anomalies"
                redis_client.set(cache_key, json.dumps(ids))
            except Exception as e:
                print(f"[RCA] Warning: Could not cache anomaly IDs in Redis: {e}", file=sys.stderr)

        mongo_client = self.get_mongo_client()
        if mongo_client:
            try:
                db = mongo_client[self.mongo_db_name]
                db["rca_session_ids"].update_one(
                    {"session_id": session_id},
                    {"$set": {"session_id": session_id, "anomaly_ids": ids, "count": len(ids)}},
                    upsert=True
                )
            except Exception as e:
                print(f"[RCA] Warning: Could not write session anomaly IDs to MongoDB: {e}", file=sys.stderr)

        return ids

    def get_session_anomaly_ids(self, session_id: str) -> List[str]:
        """Get all anomaly IDs for a session/file directly from Redis cache (falling back to Mongo)."""
        redis_client = self.get_redis_client()
        cache_key = f"rca:session:{session_id}:anomalies"
        if redis_client:
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    return json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
            except Exception:
                pass

        mongo_client = self.get_mongo_client()
        if mongo_client:
            try:
                db = mongo_client[self.mongo_db_name]
                doc = db["rca_session_ids"].find_one({"session_id": session_id})
                if doc and "anomaly_ids" in doc and doc["anomaly_ids"]:
                    ids = doc["anomaly_ids"]
                    if redis_client:
                        try:
                            redis_client.set(cache_key, json.dumps(ids))
                        except Exception:
                            pass
                    return ids
            except Exception:
                pass

        return []

    def get_cached_result(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Attempt to fetch result from Redis first, falling back to MongoDB."""
        redis_client = self.get_redis_client()
        cache_key = f"rca:incident:{incident_id}"
        if redis_client:
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    return json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
            except Exception:
                pass

        mongo_client = self.get_mongo_client()
        if mongo_client:
            try:
                db = mongo_client[self.mongo_db_name]
                doc = db["rca_results"].find_one({"incident_id": incident_id})
                if doc:
                    doc.pop("_id", None)
                    if redis_client:
                        try:
                            redis_client.set(cache_key, json.dumps(doc, indent=2))
                        except Exception:
                            pass
                    return doc
            except Exception:
                pass

        return None

    def classify_anomaly(self, anomaly_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Classify anomaly record, store Version 1 in MongoDB (rca_results) and Version 2 in Redis (rca:incident:id)."""
        incident_id = anomaly_doc.get("incident_id", "INC-000000")
        f = extract_features(anomaly_doc)

        matched_id, ev = 'C15', []
        if not f['demand_confirmed_broad']:
            matched_id, ev = 'C15', []
        else:
            matched_id, ev = evaluate_priority_1_to_4(f, self._kpi_rules or {"rules": []})
            if matched_id is None:
                matched_id, ev = evaluate_priority_5_to_6(f, self._kpi_rules or {"rules": []})
            if matched_id is None:
                matched_id, ev = evaluate_fallback(f, self._kpi_rules or {"rules": []}), []

        id_to_cause, id_to_subcat = build_lookup_maps(self._causes or {})
        subcat_info = id_to_subcat.get(matched_id, {"category": "Coverage", "subcategory": "General Degraded", "parent_id": matched_id})
        category = subcat_info['category']
        cause_entry = id_to_cause.get(matched_id, {"name": "Performance Degradation", "reason_template": "Performance degraded"})

        if matched_id == subcat_info['parent_id']:
            problem_name = subcat_info['subcategory']
        else:
            problem_name = f"{subcat_info['subcategory']} - {cause_entry['name']}"

        reason = build_reason(matched_id, f, id_to_cause)
        actions, refs = build_solution(matched_id, ev, self._solutions or {})
        supporting_evidence = build_supporting_evidence(ev, f, id_to_cause)

        kpi_raw = {
            'rlf_event_present': f.get('rlf_present'),
            'actual_throughput_mbps': f.get('actual_tp'),
            'expected_throughput_mbps': f.get('expected_tp'),
            'rsrp_dbm': f.get('rsrp'),
            'rsrq_db': f.get('rsrq'),
            'sinr_db': f.get('sinr'),
            'cqi': f.get('cqi'),
            'mcs': f.get('mcs'),
            'bler_pct': f.get('bler'),
            'rb_usage_pct': f.get('rb_usage'),
            'cell_prb_utilization_pct': f.get('cell_prb_util'),
            'carrier_count': f.get('carrier_count'),
            'lte_rank': f.get('rank'),
            'near_handover_mobility_flag': f.get('near_ho'),
            'ue_speed_kmh': f.get('ue_speed'),
            'serving_minus_best_neighbor_rsrp': f.get('gap_rsrp'),
            'handover_count_pm5s': f.get('ho_count_pm5s'),
            'near_rach_failure_flag': f.get('near_rach_fail'),
            'neighbor_cell_availability_pct': f.get('neighbor_avail'),
            'scell_rsrp_dbm': f.get('scell_rsrp'),
            'scell_sinr_db': f.get('scell_sinr'),
            'scell_cqi': f.get('scell_cqi'),
            'scell_bler_pct': f.get('scell_bler'),
        }
        kpi_evidence = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in kpi_raw.items() if v is not None}

        result = {
            'incident_id': incident_id,
            'diagnosis': {
                'category': category,
                'problem_name': problem_name,
                'reason': reason,
                'cause_id': matched_id,
                'severity': f.get('severity', 'Medium'),
            },
            'key_kpi_evidence': kpi_evidence,
            'recommended_solution': {
                'recommended_actions': actions,
                'standards_and_vendor_references': refs,
            },
        }
        if supporting_evidence:
            result['supporting_evidence'] = supporting_evidence

        # Call ran-rca-explanation-service -- send the FULL reason-matching
        # result JSON so the LLM can read the complete diagnosis, KPI
        # evidence, recommended solutions, and supporting evidence.
        explanation = None
        explanation_url = os.environ.get("RCA_EXPLANATION_URL", "http://ran-rca-explain:8010/explain")
        try:
            import urllib.request
            req_data = json.dumps(result, default=str).encode('utf-8')
            req = urllib.request.Request(explanation_url, data=req_data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=120) as response:
                if response.status == 200:
                    explanation = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"[RCA] LLM explanation service call skipped/failed ({e}); using structured fallback narrative.", file=sys.stderr)

        if not explanation:
            ev_list = [f"{k.replace('_', ' ').title()}: {v}" for k, v in list(kpi_evidence.items())[:6]]
            explanation = {
                "explanation": (
                    f"Incident {incident_id}: {problem_name} ({category}). "
                    f"Cause: {reason}. "
                    f"Key RF metrics — RSRP: {f.get('rsrp', 'N/A')} dBm, SINR: {f.get('sinr', 'N/A')} dB, "
                    f"Actual TP: {f.get('actual_tp', 'N/A')} Mbps vs Expected: {f.get('expected_tp', 'N/A')} Mbps. "
                    f"Recommended actions: {'; '.join(actions) if actions else 'Perform RF optimization on serving cell.'}."
                ),
            }

        result['explanation'] = explanation

        # Store Version 1 in MongoDB
        mongo_client = self.get_mongo_client()
        if mongo_client:
            try:
                db = mongo_client[self.mongo_db_name]
                db["rca_results"].update_one(
                    {"incident_id": incident_id},
                    {"$set": result},
                    upsert=True
                )
            except Exception as e:
                print(f"[RCA] Warning: Could not write result to MongoDB: {e}", file=sys.stderr)

        # Store Version 2 in Redis
        redis_client = self.get_redis_client()
        if redis_client:
            try:
                cache_key = f"rca:incident:{incident_id}"
                redis_client.set(cache_key, json.dumps(result, indent=2))
            except Exception as e:
                print(f"[RCA] Warning: Could not write result to Redis: {e}", file=sys.stderr)

        return result
