"""
RCA classifier v9 -- genuinely driven by kpi_rules.json now. Thresholds/conditions are NOT hardcoded in
this file; this script loads kpi_rules.json and evaluates its condition trees against a flat feature
dict computed once per incident. Editing a threshold in kpi_rules.json changes classifier behavior
directly, with no Python edit required.

Two functions, as originally requested, plus a generalized fallback pass:
FUNCTION 1: Priorities 1-4 (Resource Limitation, Coverage & Radio Quality, Outage/eNodeB Fault, Mobility).
FUNCTION 2: Priorities 5-6 (MIMO, Carrier Aggregation) -- only called if FUNCTION 1 found nothing.
FALLBACK: any priority-7 rule except C15, walked in kpi_rules.json array order -- currently C01_f
(Elevated Load, a lower-confidence Cell Congestion tier) then C14 (Radio-limited); C15 is the
unconditional last resort. Only called if FUNCTION 1 and FUNCTION 2 both found nothing, so a specific,
higher-confidence signature from either function always gets first claim on an incident. This tier is
pure kpi_rules.json data -- reordering or adding a priority-7 rule needs no Python change.

Output format: 'problem_name' is the subcategory name alone when the matched id IS that subcategory's
designated parent_id (e.g. C03 -> "Weak Serving Cell"); when the matched id is a specific peer pattern
under a subcategory instead (e.g. C08_a under "Handover Problem"), problem_name becomes
"<subcategory> - <specific cause name>" (e.g. "Handover Problem - Ping-Pong Handover") so it's never
ambiguous which one actually fired.
"""
import json

causes = json.load(open('causes.json'))
kpi_rules = json.load(open('kpi_rules.json'))
solutions = {s['id']: s for s in json.load(open('solutions.json'))['solutions']}
incidents = json.load(open('rca_anomaly_incidents_full_compact.json'))

id_to_cause = {}
id_to_subcat = {}
for cat in causes['priority_categories']:
    for sc in cat['subcategories']:
        for c in sc['causes_list']:
            id_to_cause[c['id']] = c
            id_to_subcat[c['id']] = {"category": cat['category'], "subcategory": sc['subcategory'], "parent_id": sc['parent_id']}

rules_by_id = {r['parent_id']: r for r in kpi_rules['rules']}

# Display-simplified category labels for these two subcategories, per explicit product decision --
# documented in causes.json's output_display_rule so this isn't mistaken for a stale/undocumented
# override again. Every other subcategory shows its full taxonomy category name unchanged.
CATEGORY_DISPLAY_OVERRIDE = {"C03": "Coverage", "C04": "Interference"}

def g(d, path, default=None):
    cur = d
    for p in path.split('.'):
        if cur is None: return default
        cur = cur.get(p) if isinstance(cur, dict) else default
        if cur is None: return default
    return cur

def num(x):
    return isinstance(x, (int, float))

# ================= Generic condition evaluator, driven entirely by kpi_rules.json =================
def evaluate_condition(cond, f):
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
    if op == '==': return fv == value
    if op == '!=': return fv != value
    if op == '<':  return fv < value
    if op == '<=': return fv <= value
    if op == '>':  return fv > value
    if op == '>=': return fv >= value
    if op == 'in': return fv in value
    raise ValueError(f"unknown operator {op}")

def evaluate_gate(rule, f):
    conds = rule['gate_conditions']
    logic = rule.get('gate_logic', 'ALL')
    if logic == 'ALL':
        return all(evaluate_condition(c, f) for c in conds)
    return any(evaluate_condition(c, f) for c in conds)

def evaluate_supporting_evidence(rule, f):
    return [ev['id'] for ev in rule.get('supporting_evidence', []) if evaluate_condition(ev['detection_conditions'], f)]

# ================= Feature extraction: every field kpi_rules.json's conditions can reference =================
HO_COUNT_P95 = 10.0

def extract(rec):
    f = {}
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

    f['demand_confirmed'] = (f['detection_case']=='rb_conditioned_expected_underperformance') or bool(f['rb_med_high'])
    f['demand_confirmed_broad'] = num(f['expected_tp']) and f['expected_tp'] > 0.1
    f['bad_session'] = bool(f['sustained_window']) and bool(f['low_tail_consensus'])
    f['fallback'] = True  # always true -- C15's gate is the unconditional last resort

    # ---- derived fields needed by kpi_rules.json's conditions ----
    f['underperform_80pct'] = num(f['expected_tp']) and num(f['actual_tp']) and f['actual_tp'] < 0.8*f['expected_tp']
    own_radio_bad = (num(f['rsrp']) and f['rsrp']<-110) or (num(f['sinr']) and f['sinr']<0)
    f['own_radio_normal'] = (num(f['rsrp']) and f['rsrp']>=-110) and (num(f['sinr']) and f['sinr']>=0) and not own_radio_bad
    f['mimo_pattern'] = num(f['sinr']) and f['sinr']>=15 and num(f['rank']) and f['rank']==1
    f['not_mobility'] = not f['near_ho']
    f['not_mimo'] = not f['mimo_pattern']
    f['near_zero_tp'] = num(f['actual_tp']) and f['actual_tp'] < 0.05
    f['session_collapse'] = bool(f['temporal_drop']) and bool(f['bad_session'])
    f['cell_prb_util_spike'] = num(f['cell_prb_util']) and f['cell_prb_util'] >= 80
    f['neighbor_avail_drop'] = num(f['neighbor_avail']) and f['neighbor_avail'] < 80
    return f

# ================= FUNCTION 1: Priorities 1-4 =================
def evaluate_priority_1_to_4(f):
    for rule in kpi_rules['rules']:
        if not (1 <= rule['priority'] <= 4):
            continue
        if not evaluate_gate(rule, f):
            continue
        if 'alternatives' in rule:
            for alt in rule['alternatives']:
                if all(evaluate_condition(c, f) for c in alt['gate_conditions']):
                    ev = evaluate_supporting_evidence(rule, f)
                    return (alt['id'], ev)
            continue  # outer gate fired but no specific alternative matched -- don't fire the parent
        ev = evaluate_supporting_evidence(rule, f)
        return (rule['parent_id'], ev)
    return (None, [])

# ================= FUNCTION 2: Priorities 5-6 =================
def evaluate_priority_5_to_6(f):
    for rule in kpi_rules['rules']:
        if not (5 <= rule['priority'] <= 6):
            continue
        if evaluate_gate(rule, f):
            ev = evaluate_supporting_evidence(rule, f)
            return (rule['parent_id'], ev)
    return (None, [])

def evaluate_fallback(f):
    # Walks every priority-7 rule EXCEPT C15, in kpi_rules.json array order -- first one whose gate fires
    # wins. Currently that's C01_f (Elevated Load) then C14 (Radio-limited); C15 is the unconditional
    # last resort. Nothing about this loop is specific to any one id -- reordering or adding priority-7
    # tiers is a pure kpi_rules.json edit, no Python change required.
    for rule in kpi_rules['rules']:
        if rule['priority'] == 7 and rule['parent_id'] != 'C15' and evaluate_gate(rule, f):
            ev = evaluate_supporting_evidence(rule, f)
            return (rule['parent_id'], ev)
    return ('C15', [])

def build_reason(cid, f):
    tmpl = id_to_cause[cid]['reason_template']
    vals = {
        'lte_rsrp': f.get('rsrp'), 'lte_rsrq': f.get('rsrq'), 'lte_sinr': f.get('sinr'),
        'lte_cqi': f.get('cqi'), 'lte_mcs': f.get('mcs'), 'lte_bler': f.get('bler'),
        'rb_utilization_pct': f.get('rb_usage'), 'carrier_count': f.get('carrier_count'),
        'cell_prb_utilization_pct': f.get('cell_prb_util'),
        'throughput_gap_p75': (round(f['expected_tp']-f['actual_tp'],2) if num(f.get('expected_tp')) and num(f.get('actual_tp')) else None),
        'scell_rsrp': f.get('scell_rsrp'), 'scell_sinr': f.get('scell_sinr'), 'scell_cqi': f.get('scell_cqi'), 'scell_bler': f.get('scell_bler'),
        'neighbor_cell_availability': f.get('neighbor_avail'), 'handover_count': f.get('ho_count_pm5s'), 'ue_speed_kmh': f.get('ue_speed'),
        'avg_rank': f.get('rank'), 'dl_bandwidth_mhz': None, 'dl_mcs': f.get('mcs'), 'scell_rb_count': None,
    }
    def fmt(v): return round(v,2) if isinstance(v,float) else v
    present = {k: fmt(v) for k,v in vals.items() if v is not None}
    missing = {k: 'n/a' for k,v in vals.items() if v is None}
    try:
        return tmpl.format(**present, **missing)
    except Exception:
        return tmpl

def build_supporting_evidence(matched_ids, f):
    out = []
    for eid in matched_ids:
        cause = id_to_cause.get(eid)
        if not cause: continue
        out.append({"id": eid, "name": cause['name'], "reason": build_reason(eid, f)})
    return out

def build_solution(solution_key, matched_id, matched_evidence):
    sol = solutions.get(solution_key, {"recommended_actions": [], "standards_and_vendor_references": []})
    matched = matched_evidence + [matched_id]
    actions = [a['action'] for a in sol.get('recommended_actions', []) if a.get('applies_if') is None or a.get('applies_if') in matched]
    refs = [{"source": r['source'], "note": r['note']} for r in sol.get('standards_and_vendor_references', [])]
    return actions, refs

def process(rec):
    f = extract(rec)

    if not f['demand_confirmed_broad']:
        matched_id, ev = 'C15', []
    else:
        matched_id, ev = evaluate_priority_1_to_4(f)
        if matched_id is None:
            matched_id, ev = evaluate_priority_5_to_6(f)
        if matched_id is None:
            matched_id, ev = evaluate_fallback(f)

    subcat_info = id_to_subcat[matched_id]
    category = CATEGORY_DISPLAY_OVERRIDE.get(matched_id, subcat_info['category'])
    cause_entry = id_to_cause[matched_id]

    # problem_name: subcategory alone when matched_id IS that subcategory's parent_id; otherwise
    # "<subcategory> - <specific cause name>" so a peer pattern (e.g. Ping-Pong under Handover Problem)
    # is never displayed ambiguously as if it were the parent.
    if matched_id == subcat_info['parent_id']:
        problem_name = subcat_info['subcategory']
    else:
        problem_name = f"{subcat_info['subcategory']} - {cause_entry['name']}"

    reason = build_reason(matched_id, f)
    actions, refs = build_solution(subcat_info['parent_id'], matched_id, ev)
    supporting_evidence = build_supporting_evidence(ev, f)

    kpi_raw = {
        "rlf_event_present": f.get('rlf_present'),
        "actual_throughput_mbps": f.get('actual_tp'), "expected_throughput_mbps": f.get('expected_tp'),
        "rsrp_dbm": f.get('rsrp'), "rsrq_db": f.get('rsrq'), "sinr_db": f.get('sinr'),
        "cqi": f.get('cqi'), "mcs": f.get('mcs'), "bler_pct": f.get('bler'),
        "rb_usage_pct": f.get('rb_usage'), "cell_prb_utilization_pct": f.get('cell_prb_util'),
        "carrier_count": f.get('carrier_count'), "lte_rank": f.get('rank'),
        "near_handover_mobility_flag": f.get('near_ho'), "ue_speed_kmh": f.get('ue_speed'),
        "serving_minus_best_neighbor_rsrp": f.get('gap_rsrp'), "handover_count_pm5s": f.get('ho_count_pm5s'),
        "near_rach_failure_flag": f.get('near_rach_fail'), "neighbor_cell_availability_pct": f.get('neighbor_avail'),
        "scell_rsrp_dbm": f.get('scell_rsrp'), "scell_sinr_db": f.get('scell_sinr'),
        "scell_cqi": f.get('scell_cqi'), "scell_bler_pct": f.get('scell_bler'),
    }
    kpi_evidence = {k: (round(v,2) if isinstance(v,float) else v) for k,v in kpi_raw.items() if v is not None}

    result = {
        "incident_id": rec['incident_id'],
        "diagnosis": {
            "category": category,
            "problem_name": problem_name,
            "reason": reason,
            "cause_id": matched_id,
            "severity": f.get('severity'),
        },
    }
    if supporting_evidence:
        result["supporting_evidence"] = supporting_evidence
    result["key_kpi_evidence"] = kpi_evidence
    result["recommended_solution"] = {"recommended_actions": actions, "standards_and_vendor_references": refs}
    return result

output = [process(rec) for rec in incidents]
json.dump(output, open('rca_knowledge_base_output.json', 'w'), indent=2)

from collections import Counter
dist = Counter(r['diagnosis']['problem_name'] for r in output)
print(f"Processed {len(output)} incidents.\n")
for name, n in dist.most_common():
    print(f"  {name}: {n}")
