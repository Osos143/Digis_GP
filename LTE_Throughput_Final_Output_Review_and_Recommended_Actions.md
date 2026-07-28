V# Final Review of the LTE Throughput Anomaly-Detection Pipeline

## Review scope

This review was performed on the two fully executed notebooks and the supplied statistical, ML, fusion, episode, incident, bad-cell-ranking, shortlist, and GeoJSON outputs.

Reviewed notebooks:

- `10. LTE_Throughput_PreAnomaly_Final_Optimized.ipynb`
- `11. LTE_Throughput_Anomaly_Detection_Final_Optimized_Review_Adjusted.ipynb`

The notebooks were executed sequentially with no stored execution errors, and every Python code cell compiles successfully.

No notebook code or output folder was modified during this review.

---

# 1. Executive verdict

The **core anomaly-detection design is strong and close to completion**:

- statistical methods remain the primary detectors;
- P10, session P10, IQR, and robust MAD are preserved;
- correlated low-tail methods are not counted as independent detector families;
- the selected HGB models generalize well across held-out sessions;
- the Q75 model is acceptably calibrated overall;
- LSTM and Isolation Forest are correctly retained as validation/context models only;
- ML-only anomalies are extremely rare and explicitly require human review;
- radio-limited anomalies are preserved as a planning/coverage RCA path;
- final RCA outputs contain cell identity and approximate location information.

However, I do **not** recommend declaring the project completely frozen yet. Four issues should be corrected first:

1. **Output folders are not cleaned before a run**, so stale PNG/CSV files can remain and appear in the final manifest.
2. **Episode persistence and episode confidence include terms that are constant for every retained episode**, so those terms do not distinguish episodes.
3. **Episode grouping is unnecessarily fragmented by the `source_index` continuity rule**, despite the verified one-second timestamp cadence.
4. **The compact RCA incident file uses peak row-level priority instead of the episode/incident priority**, creating two conflicting priority definitions for the same incident.

After those four corrections and one clean rerun, the project should be suitable for official handoff.

---

# 2. What currently passes

## 2.1 Notebook execution and structural validity

Both notebooks contain sequential execution counts and no saved error outputs.

- Notebook 10: 14 code cells executed.
- Notebook 11: 24 code cells executed.
- Python compilation check: no syntax failures in either notebook.

**Status: PASS**

---

## 2.2 Pre-anomaly table construction

The preprocessing notebook produces:

- 32,238 LTE downlink modeling rows;
- 271 sessions used by the ML section;
- canonical LTE throughput, RSRP, RSRQ, SINR, CQI, MCS, BLER, RB, CA, SCell, location, event, and session features;
- past-only event-window features for causal ML;
- symmetric event-window features reserved for offline RCA context.

The throughput distribution is plausible and sufficiently broad:

- P10: 4.99 Mbps
- median: 38.80 Mbps
- P75: 74.47 Mbps
- P90: 115.82 Mbps
- percentage below 10 Mbps: 17.21%

The download-context distributions are also similar enough to justify using all LTE-DL rows:

- active download median: 36.22 Mbps;
- outside parsed activity median: 40.29 Mbps;
- active-window percentage below 10 Mbps: 17.91%;
- outside-window percentage below 10 Mbps: 16.78%.

This supports the current decision to retain activity context as metadata rather than making it the main analysis mask.

**Status: PASS**

### Recommended clarification

`pre_anomaly_feature_table_leakage_guard.csv` is empty. This does not indicate an error; it means none of the forbidden post-anomaly prefixes existed when the table was exported. However, an empty file is ambiguous to a reviewer.

For a future edit, replace or supplement it with a one-row validation file containing:

- number of input columns;
- number of forbidden columns found;
- number removed;
- number remaining after the guard;
- explicit `PASS` or `FAIL`.

Suggested file name:

`pre_anomaly_leakage_guard_validation_summary.csv`

---

# 3. Statistical-method review

## 3.1 Low-tail detectors

Current low-tail results are:

| Method | Threshold | Flagged rows | Percentage |
|---|---:|---:|---:|
| Fixed domain reference | 10.00 Mbps | 5,549 | 17.21% |
| Global P10 | 4.99 Mbps | 3,224 | 10.00% |
| Median session P10 | 7.01 Mbps | 2,685 | 8.33% |
| Log-IQR lower fence | 0.669 Mbps | 1,279 | 3.97% |
| Robust MAD modified-Z | 0.550 Mbps | 1,145 | 3.55% |

The retained methods are useful for different purposes:

- 10 Mbps is a domain-facing low-throughput reference;
- global P10 describes the bottom tail of the complete drive test;
- session P10 detects relatively weak samples inside each session;
- IQR identifies extremely low values relative to the global log-throughput distribution;
- robust MAD identifies the most extreme robust lower tail.

**Status: PASS**

## 3.2 Important overlap interpretation

The overlap output shows:

- IQR versus MAD Jaccard similarity: 0.895;
- every MAD row is also an IQR row;
- every IQR row is also a global-P10 row;
- the current “at least two methods agree” count is exactly 1,279 rows, which is the IQR count.

Therefore, the low-tail methods form nested severity layers:

$$
\text{MAD extreme tail} \subset \text{IQR extreme tail} \subset \text{Global P10}
$$

This is not a problem because the notebook counts them as one low-level detector family. However, the term `low_tail_robust_consensus` may overstate the independence of the evidence.

### Recommended action

Keep all three visible outputs, but rename the fusion-facing concept to something such as:

- `low_tail_extreme_agreement`, or
- `low_tail_nested_severity_strength`.

Do not describe P10, IQR, and MAD as three independent confirmations.

**Priority: P1**

---

## 3.3 Fixed 10 Mbps threshold

The fixed 10 Mbps reference is reasonable for this dataset because it is close to the empirical 17th percentile; the preprocessing output reports P17 at approximately 9.86 Mbps.

However, the current `SUPPORTED_AS_DOMAIN_ANCHOR` verdict is generated by a broad heuristic comparison against four empirical thresholds. It should not be presented as formal threshold validation.

### Recommended action

Keep 10 Mbps as a domain anchor, but change the wording to:

> “Empirically positioned near the lower 17% of this drive-test distribution; retained as an interpretable domain reference, while adaptive methods provide dataset-specific detection.”

For stronger validation, add a sensitivity table for 8, 10, and 12 Mbps showing:

- row count;
- episode count;
- final incident count;
- overlap with P10/IQR/MAD;
- overlap with expected-throughput and temporal cases.

**Priority: P1**

---

## 3.4 Statistical fusion balance

The empirical component audit is healthy:

| Component | Mean |
|---|---:|
| strongest-trigger base | 44.47 |
| continuous magnitude | 55.74 |
| independent-family bonus | 1.31 |
| context/evidence bonus | 3.85 |

The continuous severity and strongest trigger dominate the score, while bonuses remain comparatively small. This is the desired behavior.

**Status: PASS**

---

# 4. ML review

## 4.1 Selected model quality

The main models generalize well:

| Model | Train R² | Test R² | Train MAE | Test MAE |
|---|---:|---:|---:|---:|
| HGB strict-causal temporal | 0.945 | 0.920 | 6.93 Mbps | 8.50 Mbps |
| HGB resource-conditioned | 0.936 | 0.899 | 7.63 Mbps | 9.76 Mbps |
| Calibrated resource Q75 | 0.836 | 0.809 | 12.42 Mbps | 13.75 Mbps |
| LSTM validation comparator | 0.807 | 0.749 | 13.31 Mbps | 14.74 Mbps |

The HGB temporal model is clearly the strongest central predictor. The resource-conditioned HGB model adds a useful independent expected-throughput view. The Q75 model should continue to be evaluated primarily through coverage and pinball loss rather than R² alone.

**Status: PASS**

## 4.2 Group-aware OOF validation

The predictive models use five session-group folds across all 32,238 rows. Each validation row is predicted by a model that did not train on that row’s session.

This is the correct OOF principle:

$$
\hat{y}_i = f_{-g(i)}(x_i)
$$

where $g(i)$ is the session containing row $i$, and $f_{-g(i)}$ is trained without that session.

The OOF results are much more trustworthy than a random row split because adjacent one-second samples from the same drive-test session cannot appear in both training and validation.

**Status: PASS**

### Missing direct review file

The detailed `ml_feature_leakage_audit.csv` was not included among the supplied files. Static inspection of the notebook confirms that:

- `*_count_pmXs` symmetric windows are explicitly forbidden;
- only `*_count_prevXs` and `*_prev_flag` event context can enter causal views;
- target, expected-throughput, anomaly-score, residual, and post-anomaly columns are excluded;
- assertions stop execution if a forbidden feature enters a model view.

This is reassuring, but the generated `ml_feature_leakage_audit.csv` should be included in the final archive.

**Priority: P1 documentation action**

---

## 4.3 Q75 calibration

Overall OOF Q75 coverage is approximately 76.28%, close to the 75% target.

Most prediction deciles are acceptable. The first two deciles are over-conservative:

- lowest decile coverage: 83.81%;
- second decile coverage: 80.68%.

These deciles have median predicted Q75 values of only 5.50 and 14.74 Mbps. Since strict ML underperformance requires expected throughput of at least 25 Mbps, this low-decile overcoverage should have limited influence on final anomaly triggers.

**Status: PASS WITH MONITORING**

### Recommended action

Keep the current model, but retain the decile calibration report as a mandatory QC output. Add a warning if any operationally eligible decile, meaning median expected Q75 at least 25 Mbps, has absolute coverage error greater than 5 percentage points.

**Priority: P2**

---

## 4.4 LSTM and Isolation Forest

LSTM:

- held-out R² is approximately 0.75;
- held-out MAE is approximately 14.74 Mbps;
- OOF availability is 83.30% because the first samples of each session do not have a complete 20-sample history.

Isolation Forest:

- marks approximately 3.10% of rows as raw unsupervised outliers;
- is used only as contextual corroboration;
- does not influence final production confidence.

Keeping both as validation-only methods is correct.

**Status: PASS**

### Naming clarification

The HGB models labeled `Q50` use squared-error regression in log-throughput space. They are central expected-throughput predictors, not mathematically strict median quantile regressors.

For future edits, rename them in plots and documentation to:

- `HGB strict-causal temporal central predictor`;
- `HGB resource-conditioned central predictor`.

The LSTM uses Q50 pinball loss and may retain the Q50 label.

**Priority: P1 documentation action**

---

## 4.5 ML anomaly strictness

Current ML results:

- 322 ML candidate rows;
- 140 final ML anomalies, equal to 0.434% of all LTE-DL rows;
- all 140 final ML anomalies have both production families;
- 4 ML-only retained rows, equal to 0.0124% of all rows;
- all ML-only rows are marked for supervised verification.

The four ML-only rows have meaningful gaps and both resource and temporal support. Their final priorities are approximately 50.3 to 55.6, which is appropriate for a supervised review queue rather than an automatic confirmed-anomaly queue.

**Status: PASS**

### Recommended shortlist change

The 15-incident diverse shortlist contains no supervised ML-only case. Reserve one optional slot for the highest-priority ML-only incident when at least one exists.

**Priority: P1**

---

# 5. Statistical–ML fusion review

## 5.1 Statistical-first behavior

The final 3,574 row-level handoff rows are distributed as:

- statistical-only: 3,434 rows, 96.08%;
- statistical + ML consensus: 136 rows, 3.81%;
- ML-only: 4 rows, 0.11%.

This strongly satisfies the requirement that statistical methods remain central.

The final row handoff represents approximately 11.09% of all 32,238 LTE-DL rows.

**Status: PASS**

---

## 5.2 Fused confidence ceilings

The current confidence logic uses:

- statistical evidence ceiling: 0.90;
- ML evidence ceiling: 0.85;
- statistical–ML agreement bonus: 0.07;
- confirmed RB-demand bonus: 0.03;
- two-production-ML-family bonus: 0.03.

The base confidence is:

$$
C_{\text{base}}
=
1-
(1-0.90E_{\text{stat}})
(1-0.85E_{\text{ML}})
$$

The ceilings are design priors, not learned probabilities. Their interpretation is:

- statistics may provide up to 90% confidence before bonuses;
- ML may provide up to 85% confidence before bonuses;
- independent agreement can raise confidence further;
- no single source is automatically treated as certainty.

The final outputs show only 2.60% of handed-off rows saturating at 100 confidence, so saturation is not excessive.

**Status: ACCEPTABLE**

### Recommended action before freezing

Create a sensitivity audit using nearby ceiling combinations:

- statistical: 0.85, 0.90, 0.95;
- ML: 0.80, 0.85, 0.90.

For each pair, report:

- number of retained rows;
- number of episodes;
- number of incidents;
- top-50 incident overlap;
- Spearman rank correlation of incident priority.

Freeze the current 0.90/0.85 values only if the top incident ranking remains stable.

**Priority: P1**

---

# 6. Episode construction: important corrections

This is the main area requiring changes.

## 6.1 Excessive fragmentation from `source_index`

An episode is currently split when either:

- timestamp gap exceeds 3 seconds; or
- `source_index` gap exceeds 1.

Among consecutive final handoff-row pairs whose timestamp gap is no more than 3 seconds:

- 1,891 pairs satisfy the time-continuity rule;
- 510 of them, or 26.97%, have `source_index` gap greater than 1 and are therefore split.

Using timestamp continuity alone would reduce the candidate episode count from approximately 2,193 to 1,683, a reduction of about 23%.

Because the project has verified a one-second cadence, `source_index` should not be a hard episode separator when timestamps remain continuous. A source-index gap can simply mean that a non-LTE or filtered row existed between two LTE-DL rows.

### Recommended action

Use the following hierarchy:

1. same session;
2. timestamp gap no more than 3 seconds;
3. same or compatible serving cell;
4. optionally compatible anomaly family.

Keep `source_index` gap as an audit field, not a mandatory split rule.

**Priority: P0 — required before official freeze**

---

## 6.2 Persistence formula contains redundant terms

Current persistence is:

$$
P_e =
100
\left(
0.40S_{\text{rows}}
+
0.30S_{\text{span}}
+
0.20S_{\text{run}}
+
0.10D
\right)
$$

where:

- $S_{\text{rows}}$ is observed anomalous seconds normalized by 10;
- $S_{\text{span}}$ is inclusive span normalized by 30;
- $S_{\text{run}}$ is longest consecutive run normalized by 10;
- $D$ is episode density.

In the supplied final episode table:

- `episode_density_0_1` is exactly 1.0 for all 1,490 episodes;
- observed anomalous seconds equals inclusive span;
- longest run also equals row count for all retained episodes.

Therefore, the four terms are mostly repeated measurements of the same thing. Every one-second singleton automatically receives a persistence score of 17.

The final episodes are highly short:

- 46.78% are singletons;
- 79.73% contain at most two rows;
- 92.15% contain at most three rows.

### Recommended action

After correcting episode grouping, simplify persistence to genuinely distinct dimensions. A suitable incident-level form is:

$$
P^* =
100
\left(
0.50\min\left(\frac{L_{\max}}{10},1\right)
+
0.30\min\left(\frac{S_{\text{anomalous}}}{20},1\right)
+
0.20\min\left(\frac{N_{\text{episodes}}}{3},1\right)
\right)
$$

where:

- $L_{\max}$ is the longest uninterrupted anomalous run;
- $S_{\text{anomalous}}$ is total anomalous time;
- $N_{\text{episodes}}$ is recurrence inside the consolidated incident.

Alternatively, keep the current formula but remove the density term and avoid simultaneously using rows, span, and longest run when they are identical.

**Priority: P0 — required before official freeze**

---

## 6.3 Direct-evidence coverage is constant

`direct_evidence_coverage_0_1` is exactly 1.0 for every retained episode.

The current calculation sums multiple direct flags and divides by episode rows, then clips at 1. Because each retained anomaly row already contains one or more direct flags, and several rows have multiple flags, the value always saturates.

As a result, episode confidence receives a constant 10-point contribution from direct evidence:

$$
C_e =
0.50C_{\max}
+
0.25C_{\text{mean}}
+
0.15A
+
0.10E
$$

with $E=1$ for every episode.

This term does not distinguish strong episodes from weak ones.

### Recommended action

Define a single row-level boolean such as `high_quality_direct_evidence_row`, based only on strong evidence:

- reliable radio- or RB-conditioned P75;
- confirmed RB inefficiency under medium/high demand;
- CA underperformance under medium/high RB demand;
- radio-limited degradation with explicit poor-radio evidence;
- temporal drop exceeding the strong drop threshold;
- two-family production-ML agreement.

Then compute:

$$
E =
\frac{\text{rows with high-quality direct evidence}}
{\text{episode rows}}
$$

Do not sum multiple flags for the same row.

**Priority: P0 — required before official freeze**

---

## 6.4 Episode confidence threshold is effectively bypassed

The episode keep rule currently allows an episode when:

- episode confidence reaches the threshold; **or**
- `strong_direct_evidence_rows > 0`.

Because all final episodes have direct evidence coverage of 1.0, the confidence threshold is effectively bypassed.

### Recommended action

After correcting the direct-evidence definition:

- require the episode-confidence threshold normally;
- allow an override only for explicitly critical impact, such as episode impact at least 80 with a verified direct detector;
- export the override reason.

Suggested fields:

- `episode_keep_path`;
- `episode_confidence_gate_pass`;
- `episode_critical_override_flag`;
- `episode_critical_override_reason`.

**Priority: P0 — required before official freeze**

---

# 7. Operational incident consolidation

Operational consolidation reduces:

- 1,490 strict episodes;
- to 1,302 incidents;
- a 12.62% reduction.

Only 9.68% of incidents contain more than one strict episode. This is reasonable, but the reduction will likely become more meaningful after fixing source-index fragmentation.

The current bridging conditions are sensible:

- same session;
- no more than 5 seconds apart;
- no more than 50 meters apart when coordinates are available;
- same serving cell, or compatible PCI fallback;
- matching statistical, ML, or dominant-impact family.

**Status: LOGICALLY SOUND, BUT DEPENDENT ON EPISODE FIX**

### Recommended action

Retain operational consolidation, but rerun its sensitivity after fixing episodes:

- gap thresholds: 3, 5, and 8 seconds;
- distance thresholds: 30, 50, and 100 meters.

Report incident-count stability and top-incident stability.

**Priority: P1**

---

# 8. Conflicting incident priorities

This is a major handoff inconsistency.

The operational-incident table uses episode-level priorities. Its maximum incident priority is 86.30.

The compact RCA shortlist instead assigns:

- priority = maximum row-level fused priority;
- impact = maximum row-level impact;
- confidence = maximum row-level confidence.

This produces shortlist priorities as high as 98.96 for incidents whose operational incident priority is only around 81.

For example:

| Incident | Compact RCA priority | Operational priority |
|---|---:|---:|
| INC-000413 | 98.96 | 81.06 |
| INC-000951 | 97.83 | 81.55 |
| INC-000612 | 94.43 | 77.98 |
| INC-000416 | 92.49 | 76.20 |

Therefore, the episode persistence and episode-confidence calculations are not actually controlling the priority used in the final compact handoff.

### Recommended action

Use one canonical incident priority.

Recommended fields:

- `peak_row_priority_0_100`;
- `episode_adjusted_priority_0_100`;
- `incident_final_priority_0_100`.

Set `incident_final_priority_0_100` to the operational incident priority used for ranking. Keep peak row priority only as supporting severity context.

Also derive incident severity from the maximum ordered severity, not the statistical mode of row labels.

**Priority: P0 — required before official freeze**

---

# 9. RCA shortlist diversity

The current 15-incident shortlist contains:

- 3 CA-underperformance incidents;
- 3 radio-limited incidents;
- 3 temporal local-drop incidents;
- 2 sudden-drop incidents;
- 2 RB-conditioned expected-underperformance incidents;
- 2 radio-conditioned expected-underperformance incidents.

It contains:

- 7 Critical;
- 7 High;
- 1 Medium;
- 3 planning/coverage-review cases;
- 0 supervised ML-only cases;
- 0 explicit RB-efficiency cases.

The shortlist is substantially better than a pure top-score list, but it still does not represent all important final pathways.

### Recommended action

Reserve shortlist slots in this order:

1. radio-limited/planning;
2. CA underperformance;
3. temporal local drop;
4. sudden drop;
5. RB-conditioned underperformance;
6. radio-conditioned underperformance;
7. RB-efficiency underperformance;
8. one supervised ML-only case when available;
9. remaining slots filled by canonical incident priority with cell/session deduplication.

**Priority: P1**

---

# 10. Worst-performing cell and PCI ranking

The ranking combines throughput, anomaly rate, P75 gap, CQI, MCS, BLER, SINR, RSRQ, and RSRP. The weights correctly keep throughput as the primary definition of poor performance.

However, among the top 25 ranked cells:

- 11 have LOW reliability;
- 8 have MEDIUM reliability;
- 6 have HIGH reliability.

A low-reliability cell may have only 30–49 rows or limited session coverage. It is useful as a watchlist candidate, but it should not be presented as a confirmed worst cell with the same confidence as a repeatedly observed cell.

### Recommended action

Export two separate lists:

1. `worst_performing_cells_confirmed.csv`
   - HIGH and MEDIUM reliability;
2. `worst_performing_cells_watchlist_low_reliability.csv`
   - LOW reliability.

Keep the complete ranked file as an internal audit table.

For the dashboard, display both:

- bad-cell score;
- ranking reliability.

**Priority: P1**

---

# 11. ECI location and map review

The GeoJSON contains 457 unique cell keys with valid coordinates.

The location method is correctly described as the median anomaly-observation coordinate, not a guaranteed tower coordinate.

Important uncertainty findings:

- 43.33% of cell markers use at most two anomalous GPS rows;
- 68.49% use at most five rows;
- median P90 observation spread: 38.6 meters;
- 90th-percentile spread: 748 meters;
- maximum spread: approximately 5.3 kilometers.

A large spread may indicate:

- a wide serving footprint;
- repeated observations along a route;
- PCI/ECI behavior over a broad area;
- insufficient observations;
- the fact that this is a served-location centroid rather than a tower coordinate.

### Recommended action

Add:

- `location_reliability`;
- `location_uncertainty_radius_m`;
- `location_is_tower_coordinate = false`;
- `location_method = anomaly_observation_centroid`.

Suggested reliability:

- HIGH: at least 10 GPS anomaly rows and P90 spread no more than 100 m;
- MEDIUM: at least 5 rows and spread no more than 500 m;
- LOW: otherwise.

On the dashboard:

- draw an uncertainty circle;
- use a different marker style for LOW reliability;
- never label the point as the physical eNodeB location unless a planning-site database supplies the actual site coordinates.

**Priority: P1**

---

# 12. Radio-limited anomalies

Radio-limited degradation is the largest final row-level case:

- 1,553 of 3,574 final rows;
- median actual throughput: approximately 2.50 Mbps;
- median RSRP: approximately -104.7 dBm;
- median SINR: approximately 6.0 dB;
- median BLER: approximately 13.1%;
- all are marked for coverage/planning review.

These are important and should remain in the final RCA flow.

However, because they represent a large share of the handoff, they can dominate a general incident queue.

### Recommended action

Provide a dedicated planning queue:

`rca_radio_limited_planning_incidents.csv`

Include:

- ECI, PCI, EARFCN and band;
- approximate observation centroid and uncertainty;
- RSRP, RSRQ, SINR, CQI, MCS and BLER;
- neighbor context where available;
- bad-cell rank;
- recurrence across sessions;
- priority and confidence;
- likely planning investigation themes.

Keep radio-limited incidents in the main handoff as well.

**Priority: P1**

---

# 13. Output-folder freshness

The current notebooks do not clear generated output folders before execution.

There is direct evidence of stale output mixing:

- Notebook 10’s output index already contains anomaly/fusion plot names that are produced only by Notebook 11.
- Notebook 11’s final index contains both older plot names and the newer review-adjusted plot names.

Therefore, the output manifests cannot guarantee that every PNG belongs to the most recent run.

### Required future action

At the beginning of a full production run:

1. delete only generated folders;
2. recreate the expected structure;
3. run Notebook 10;
4. run Notebook 11;
5. generate the output manifests only after all exports complete.

Folders to clean:

- `01_preprocessing_cleaning`
- `02_anomaly_detection/01_statistical_csv`
- `02_anomaly_detection/02_ml_csv`
- `02_anomaly_detection/03_fusion_csv`
- `03_plots`
- `04_rca_handoff_final`

Do not delete `Raw_Data`.

A run-specific alternative is:

`Throughput_Anomaly_Detection_Outputs/run_YYYYMMDD_HHMMSS/`

This provides stronger reproducibility and allows old runs to be archived intentionally rather than mixed accidentally.

**Priority: P0 — required before final rerun**

---

# 14. Markdown equation formatting standard

For all future Markdown and notebook documentation:

- inline equation: `$equation$`
- separate display equation:

```markdown
$$
equation
$$
```

Do not use `\(...\)` or `\[...\]` because they do not render correctly in the user’s local Markdown environment.

This review file follows the requested `$...$` and `$$...$$` convention.

---

# 15. Recommended action order

## P0 — complete before official freeze

1. Add safe generated-output cleanup before a production run.
2. Remove `source_index > 1` as an automatic episode split when timestamps are continuous.
3. Redesign episode persistence so its components are not duplicates.
4. Redesign direct-evidence coverage so it is not always 1.
5. Prevent direct evidence from automatically bypassing the episode-confidence gate.
6. Use one canonical incident priority in the operational table, compact CSV/JSON, shortlist, and plots.
7. Rerun both notebooks from a clean output directory and regenerate all manifests.

## P1 — strongly recommended

1. Add fusion-ceiling sensitivity and ranking-stability audits.
2. Rename low-tail “consensus” as nested extreme-tail agreement.
3. Improve the 10 Mbps threshold-validation wording and add 8/10/12 Mbps sensitivity.
4. Rename HGB Q50 models as central predictors.
5. Include `ml_feature_leakage_audit.csv` in the final review package.
6. Add an RB-efficiency and supervised ML-only slot to the diverse shortlist.
7. Separate confirmed bad cells from low-reliability watchlist cells.
8. Add map-location reliability and uncertainty visualization.
9. Export a dedicated radio-limited planning queue.
10. Test incident consolidation at nearby time and distance thresholds.

## P2 — cleanup and presentation

1. Add a machine-readable sampling-gap summary CSV.
2. Add Q75 operational-decile warnings.
3. Add a run metadata file containing run timestamp, notebook hashes, input-file hash, row counts, and output counts.
4. Keep the 638-column fused table internal; continue using compact incident JSON for RCA.

---

# 16. Final acceptance criteria

The anomaly-detection part can be officially declared complete when:

- both notebooks run from a clean output folder with zero errors;
- output manifests contain only files created in that run;
- causal leakage assertions pass and the detailed leakage audit is archived;
- HGB and Q75 metrics remain close to the current results;
- statistical-first proportions remain dominant;
- ML-only incidents remain rare and supervised;
- timestamp-based episode grouping produces technically coherent episodes;
- episode density/direct-evidence fields are no longer constant;
- episode confidence gates are actually active;
- operational and compact RCA files use the same canonical incident priority;
- the shortlist includes the main statistical, planning, resource, temporal, RB-efficiency, and supervised-ML pathways;
- bad-cell and map outputs display reliability;
- top anomaly plots clearly show pre-anomaly context and episode boundaries.

---

# Final recommendation

The statistical and ML foundations are good enough to retain. The strongest parts are the session-group OOF validation, the causal HGB temporal model, the calibrated Q75 reference, the statistical-first fusion, and the explicit planning treatment of radio-limited cases.

The remaining work is concentrated in **episode construction, episode confidence/persistence, final incident priority consistency, and reproducible output cleanup**. These are not new anomaly-detection features. They are final correctness and handoff-governance fixes.

Once the P0 items are corrected and the notebooks are rerun into a clean folder, the project should be ready for formal completion and RCA handoff.
