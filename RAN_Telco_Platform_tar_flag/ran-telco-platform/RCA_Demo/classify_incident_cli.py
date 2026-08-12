#!/usr/bin/env python3
"""RCA classifier CLI for a single anomaly loaded from MongoDB and cached in Redis."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from pymongo import MongoClient
import redis

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DB = "rca"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_CAUSES_PATHS = ["causes.json", "causes (1).json"]
DEFAULT_KPI_RULES_PATHS = ["kpi_rules.json", "kpi_rules (1).json"]
DEFAULT_SOLUTIONS_PATHS = ["solutions.json"]
DEFAULT_ANOMALIES_PATHS = ["rca_anomaly_incidents_full_compact.json"]
DEFAULT_CACHE_PREFIX = "rca:incident:"


def g(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur = d
    for p in path.split('.'):
        if cur is None:
            return default
        if not isinstance(cur, dict):
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


HO_COUNT_P95 = 10.0


def extract(rec: Dict[str, Any]) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    f['rsrp'] = g(rec, 'radio_kpis.rsrp_median_dbm')
    f['rsrq'] = g(rec, 'radio_kpis.rsrq_median_db')
    f['sinr'] = g(rec, 'radio_kpis.sinr_median_db')
    f['cqi'] = g(rec, 'radio_kpis.cqi_median')
    f['mcs'] = g(rec, 'radio_kpis.mcs_median')
    f['bler'] = g(rec, 'radio_kpis.bler_median_pct')
    f['rb_usage'] = g(rec, 'resource_kpis.rb_usage_median')
    f['tp_per_rb'] = g(rec, 'resource_kpis.throughput_per_rb_median')
    f['rb_med_high'] = g(rec, 'resource_kpis.rb_medium_or_high_usage', False)
    f['actual_tp'] = g(rec, 'throughput.actual_median_mbps')
    f['expected_tp'] = g(rec, 'throughput.expected_median_mbps')
    f['ca_active'] = g(rec, 'ca_context.ca_active', False)
    f['carrier_count'] = g(rec, 'ca_context.carrier_count_median')
    f['scell_rsrp'] = g(rec, 'ca_context.scell1_rsrp_median_dbm')
    f['scell_sinr'] = g(rec, 'ca_context.scell1_sinr_median_db')
    f['scell_cqi'] = g(rec, 'ca_context.scell1_cqi_median')
    f['scell_bler'] = g(rec, 'ca_context.scell1_bler_median_pct')
    f['temporal_drop'] = g(rec, 'statistical_evidence.temporal_drop', False)
    f['sustained_window'] = g(rec, 'statistical_evidence.sustained_window', False)
    f['low_tail_consensus'] = g(rec, 'statistical_evidence.low_tail_consensus', False)
    f['detection_case'] = rec.get('detection_case')
    f['severity'] = rec.get('severity')
    f['cell_prb_util'] = g(rec, 'rca_required_kpis.cell_prb_utilization_pct')
    f['near_ho'] = bool(g(rec, 'rca_required_kpis.near_handover_mobility_flag', False))
    f['near_rach_fail'] = bool(g(rec, 'rca_required_kpis.near_rach_failure_flag', False))
    f['neighbor_avail'] = g(rec, 'rca_required_kpis.neighbor_cell_availability')
    f['rank'] = g(rec, 'rca_required_kpis.lte_rank')
    f['ue_speed'] = g(rec, 'rca_required_kpis.ue_speed_kmh')
    f['gap_rsrp'] = g(rec, 'rca_required_kpis.serving_minus_best_neighbor_rsrp')
    f['ho_count_pm5s'] = g(rec, 'rca_required_kpis.handover_mobility_count_pm5s')
    f['ho_dwell'] = g(rec, 'rca_required_kpis.ho_dwell_time_s')
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


def evaluate_priority_1_to_4(f: Dict[str, Any], kpi_rules: Dict[str, Any]) -> tuple[Optional[str], List[str]]:
    for rule in kpi_rules['rules']:
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


def evaluate_priority_5_to_6(f: Dict[str, Any], kpi_rules: Dict[str, Any]) -> tuple[Optional[str], List[str]]:
    for rule in kpi_rules['rules']:
        if not (5 <= rule['priority'] <= 6):
            continue
        if evaluate_gate(rule, f):
            return rule['parent_id'], evaluate_supporting_evidence(rule, f)
    return None, []


def evaluate_fallback(f: Dict[str, Any], kpi_rules: Dict[str, Any]) -> str:
    for rule in kpi_rules['rules']:
        if rule['priority'] == 7 and rule['parent_id'] == 'C14' and evaluate_gate(rule, f):
            return 'C14'
    return 'C15'


def build_reason(cid: str, f: Dict[str, Any], id_to_cause: Dict[str, Dict[str, Any]]) -> str:
    tmpl = id_to_cause[cid]['reason_template']
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


def build_supporting_evidence(matched_ids: Iterable[str], f: Dict[str, Any], id_to_cause: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for eid in matched_ids:
        cause = id_to_cause.get(eid)
        if not cause:
            continue
        out.append({"id": eid, "name": cause['name'], "reason": build_reason(eid, f, id_to_cause)})
    return out


def build_solution(parent_id: str, matched_evidence: List[str], solutions: Dict[str, Dict[str, Any]]) -> tuple[List[str], List[Dict[str, str]]]:
    sol = solutions.get(parent_id, {"recommended_actions": [], "standards_and_vendor_references": []})
    matched = set(matched_evidence + [parent_id])
    actions = [a['action'] for a in sol.get('recommended_actions', []) if a.get('applies_if') is None or a.get('applies_if') in matched]
    refs = [{"source": r['source'], "note": r['note']} for r in sol.get('standards_and_vendor_references', [])]
    return actions, refs


def build_lookup_maps(causes: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
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


def load_json_file(paths: List[str], workdir: str) -> Any:
    for path in paths:
        candidate = os.path.join(workdir, path)
        if os.path.exists(candidate):
            with open(candidate, 'r', encoding='utf-8') as handle:
                return json.load(handle)
    raise FileNotFoundError(f"None of these files were found in {workdir}: {paths}")


def load_mongo_metadata(collection) -> Any:
    result = collection.find_one({'_id': 'metadata'})
    if result is None:
        result = collection.find_one({})
    if result is None:
        raise ValueError(f"Collection {collection.name} is empty")
    result.pop('_id', None)
    return result


def load_mongo_data(client: MongoClient, db_name: str, collection_names: Dict[str, str]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    db = client[db_name]
    causes = load_mongo_metadata(db[collection_names['causes']])
    kpi_rules = load_mongo_metadata(db[collection_names['kpi_rules']])
    solutions_doc = load_mongo_metadata(db[collection_names['solutions']])
    if isinstance(solutions_doc, dict) and 'solutions' in solutions_doc:
        solutions = {s['id']: s for s in solutions_doc['solutions']}
    elif isinstance(solutions_doc, list):
        solutions = {s['id']: s for s in solutions_doc}
    else:
        raise ValueError('Solutions collection must contain a document with a solutions list or a list of solution documents')

    anomalies_coll = db[collection_names['anomalies']]
    anomalies: List[Dict[str, Any]] = list(anomalies_coll.find({}))
    return causes, kpi_rules, solutions, anomalies


def bootstrap_collections(client: MongoClient, db_name: str, workdir: str, collection_names: Dict[str, str]) -> None:
    print('Bootstrapping MongoDB collections from local JSON files...')
    db = client[db_name]
    causes = load_json_file(DEFAULT_CAUSES_PATHS, workdir)
    kpi_rules = load_json_file(DEFAULT_KPI_RULES_PATHS, workdir)
    solutions = load_json_file(DEFAULT_SOLUTIONS_PATHS, workdir)
    anomalies = load_json_file(DEFAULT_ANOMALIES_PATHS, workdir)

    db[collection_names['causes']].delete_many({})
    db[collection_names['causes']].insert_one({'_id': 'metadata', **causes})

    db[collection_names['kpi_rules']].delete_many({})
    db[collection_names['kpi_rules']].insert_one({'_id': 'metadata', **kpi_rules})

    db[collection_names['solutions']].delete_many({})
    if isinstance(solutions, dict) and 'solutions' in solutions:
        db[collection_names['solutions']].insert_one({'_id': 'metadata', **solutions})
    else:
        db[collection_names['solutions']].insert_many(solutions)

    db[collection_names['anomalies']].delete_many({})
    if isinstance(anomalies, list):
        db[collection_names['anomalies']].insert_many(anomalies)
    else:
        raise ValueError('Anomalies JSON root must be a top-level list')

    print('Bootstrap completed successfully.')


def find_anomaly(db, collection_name: str, requested: str) -> Dict[str, Any]:
    coll = db[collection_name]
    if requested.isdigit():
        index = int(requested) - 1
        if index < 0:
            raise ValueError('Anomaly number must be a positive integer')
        doc = coll.find().sort('incident_id', 1).skip(index).limit(1)
        anomaly = next(doc, None)
        if anomaly is None:
            raise ValueError(f'No anomaly at index {requested}')
        return anomaly
    anomaly = coll.find_one({'incident_id': requested})
    if anomaly is None:
        raise ValueError(f'No anomaly found for incident_id {requested}')
    return anomaly


def build_result(rec: Dict[str, Any], causes: Dict[str, Any], kpi_rules: Dict[str, Any], solutions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    id_to_cause, id_to_subcat = build_lookup_maps(causes)
    f = extract(rec)

    matched_id, ev = 'C15', []
    if not f['demand_confirmed_broad']:
        matched_id, ev = 'C15', []
    else:
        matched_id, ev = evaluate_priority_1_to_4(f, kpi_rules)
        if matched_id is None:
            matched_id, ev = evaluate_priority_5_to_6(f, kpi_rules)
        if matched_id is None:
            matched_id, ev = evaluate_fallback(f, kpi_rules), []

    subcat_info = id_to_subcat[matched_id]
    category = subcat_info['category']
    cause_entry = id_to_cause[matched_id]

    if matched_id == subcat_info['parent_id']:
        problem_name = subcat_info['subcategory']
    else:
        problem_name = f"{subcat_info['subcategory']} - {cause_entry['name']}"

    reason = build_reason(matched_id, f, id_to_cause)
    actions, refs = build_solution(matched_id, ev, solutions)
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
        'incident_id': rec['incident_id'],
        'diagnosis': {
            'category': category,
            'problem_name': problem_name,
            'reason': reason,
            'cause_id': matched_id,
            'severity': f.get('severity'),
        },
        'key_kpi_evidence': kpi_evidence,
        'recommended_solution': {
            'recommended_actions': actions,
            'standards_and_vendor_references': refs,
        },
    }
    if supporting_evidence:
        result['supporting_evidence'] = supporting_evidence
    return result


def cache_result(redis_client: redis.Redis, key: str, payload: Dict[str, Any], ttl: Optional[int] = None) -> None:
    value = json.dumps(payload, indent=2)
    if ttl is not None:
        redis_client.setex(key, ttl, value)
    else:
        redis_client.set(key, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Classify one RCA anomaly from MongoDB and store output in Redis.')
    parser.add_argument('anomaly', help='Anomaly incident_id (e.g. INC-000001) or numeric index (1-based)')
    parser.add_argument('--mongo-uri', default=os.environ.get('MONGO_URI', DEFAULT_MONGO_URI), help='MongoDB connection URI')
    parser.add_argument('--mongo-db', default=os.environ.get('MONGO_DB', DEFAULT_MONGO_DB), help='MongoDB database name')
    parser.add_argument('--mongo-causes-coll', default='causes', help='Mongo collection for causes metadata')
    parser.add_argument('--mongo-kpi-rules-coll', default='kpi_rules', help='Mongo collection for kpi rules')
    parser.add_argument('--mongo-solutions-coll', default='solutions', help='Mongo collection for solutions')
    parser.add_argument('--mongo-anomalies-coll', default='anomalies', help='Mongo collection for anomaly documents')
    parser.add_argument('--redis-url', default=os.environ.get('REDIS_URL', DEFAULT_REDIS_URL), help='Redis connection URL')
    parser.add_argument('--cache-prefix', default=os.environ.get('CACHE_PREFIX', DEFAULT_CACHE_PREFIX), help='Redis cache key prefix')
    parser.add_argument('--cache-ttl', type=int, default=None, help='Cache TTL in seconds (default: no expiration)')
    parser.add_argument('--skip-cache', action='store_true', help='Do not write output to Redis')
    parser.add_argument('--bootstrap', action='store_true', help='Load local JSON files into MongoDB before classification')
    parser.add_argument('--workdir', default=os.getcwd(), help='Directory where local JSON files are stored for bootstrap')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = MongoClient(args.mongo_uri)
    db = client[args.mongo_db]
    collection_names = {
        'causes': args.mongo_causes_coll,
        'kpi_rules': args.mongo_kpi_rules_coll,
        'solutions': args.mongo_solutions_coll,
        'anomalies': args.mongo_anomalies_coll,
    }

    if args.bootstrap:
        bootstrap_collections(client, args.mongo_db, args.workdir, collection_names)

    causes, kpi_rules, solutions, _ = load_mongo_data(client, args.mongo_db, collection_names)
    anomaly = find_anomaly(db, collection_names['anomalies'], args.anomaly)

    if '_id' in anomaly:
        anomaly.pop('_id')

    result = build_result(anomaly, causes, kpi_rules, solutions)

    if args.skip_cache:
        print(json.dumps(result, indent=2))
        print('\nSkipped Redis caching because --skip-cache was provided.')
        return 0

    redis_client = redis.from_url(args.redis_url)
    cache_key = f"{args.cache_prefix}{anomaly['incident_id']}"
    try:
        cache_result(redis_client, cache_key, result, ttl=args.cache_ttl)
        print(json.dumps(result, indent=2))
        print(f"\nCached output in Redis key: {cache_key}")
    except redis.exceptions.RedisError as exc:
        print(json.dumps(result, indent=2))
        print(f"\nWarning: could not cache result in Redis: {exc}", file=sys.stderr)
        print('Proceeding without Redis caching.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
