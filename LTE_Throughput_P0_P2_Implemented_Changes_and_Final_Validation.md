# LTE Throughput Anomaly Detection — Priority 0–2 Implementation Change Log

## 1. Purpose

This document records the final Priority 0, Priority 1, and Priority 2 corrections implemented in the two optimized notebooks:

- `10. LTE_Throughput_PreAnomaly_Final_P0_P2_Updated.ipynb`
- `11. LTE_Throughput_Anomaly_Detection_Final_P0_P2_Updated.ipynb`

The update does not introduce a new anomaly-detection family. It strengthens correctness, reproducibility, episode construction, incident ranking, validation outputs, and RCA handoff governance.

The notebooks intentionally contain no stored outputs or execution counts. They should be run in this order:

1. Notebook 10: `Restart Kernel → Run All`
2. Notebook 11: `Restart Kernel → Run All`

Notebook 10 now removes the previous generated-output tree before a production run, ensuring that the final PNG, CSV, JSON, GeoJSON, model, and manifest files all belong to the current run.

---

# 2. Priority 0 changes

## 2.1 Safe generated-output cleanup

Notebook 10 now defines:

`CLEAN_GENERATED_OUTPUTS_BEFORE_RUN = True`

At the start of a production run, it removes only:

`Throughput_Anomaly_Detection_Outputs/`

The code includes safety checks before deletion:

- the output root must have the expected folder name;
- the output root must not be a symbolic link;
- `Raw_Data/` is never removed;
- all required output subfolders are recreated immediately.

This resolves the stale-output problem where older PNG or CSV files could remain in the folder and appear in the final output manifest.

The intended production workflow is therefore:

```text
Run Notebook 10
    ↓
Previous generated outputs are removed
    ↓
Fresh preprocessing outputs are created
    ↓
Run Notebook 11
    ↓
Fresh statistical, ML, fusion, episode, incident and RCA files are created
```

---

## 2.2 Episode continuity no longer depends on `source_index`

The previous episode logic started a new episode when either:

- the timestamp gap exceeded the configured episode gap; or
- the `source_index` gap exceeded one.

The updated logic treats `source_index` as an audit field only.

An anomaly row remains in the same episode when:

- it belongs to the same session;
- its timestamp gap is no greater than three seconds;
- its serving-cell identity remains compatible when both identities are known.

The hierarchy used for serving-cell identity is:

1. `serving_cell_key`;
2. `serving_eci`;
3. `serving_earfcn + serving_pci`;
4. no cell-based split when a reliable identity is unavailable.

This prevents filtered non-LTE rows or intermediate records from unnecessarily fragmenting a technically continuous LTE throughput anomaly.

---

## 2.3 Episode persistence was redesigned

The old persistence calculation used four terms that were often identical:

- anomalous row count;
- episode span;
- longest consecutive run;
- episode density.

Because the data is sampled every second, these values frequently repeated the same information.

The updated episode persistence is:

$$
P_{\text{episode}}
=
100
\left(
0.60S_{\text{run}}
+
0.25S_{\text{anomalous time}}
+
0.15S_{\text{density}}
\right)
$$

where:

- $S_{\text{run}}$ is the longest uninterrupted anomalous run, normalized at ten seconds;
- $S_{\text{anomalous time}}$ is total observed anomalous time, normalized at twenty seconds;
- $S_{\text{density}}$ is the fraction of the episode span occupied by anomalous samples.

The notebook also exports:

- `span_seconds_inclusive`;
- `observed_anomalous_seconds`;
- `internal_gap_seconds`;
- `longest_consecutive_run_seconds`;
- `episode_density_0_1`;
- `episode_persistence_score_0_100`.

The new persistence value differentiates:

- isolated one-second anomalies;
- short dense anomalies;
- interrupted anomaly periods;
- long sustained anomalies.

---

## 2.4 Direct-evidence coverage was corrected

Previously, multiple evidence flags on one row were summed. The result was divided by the number of rows and clipped to one. Because most retained anomaly rows had several flags, episode direct-evidence coverage frequently became one for every episode.

The updated implementation creates one Boolean field per row:

`high_quality_direct_evidence_row`

A row is marked as high-quality direct evidence only when at least one strict condition is met.

Examples include:

- reliable radio-conditioned P75 underperformance with at least a 25 Mbps gap and actual/expected ratio no greater than 0.25;
- reliable RB-conditioned P75 underperformance with the same strong gap and ratio conditions;
- RB-efficiency anomaly under high RB usage;
- CA underperformance under confirmed RB demand and at least a 20 Mbps expected gap;
- radio-limited degradation supported by at least two poor-radio indicators and actual throughput no greater than 10 Mbps;
- local or sudden throughput drop of at least 15 Mbps;
- production ML agreement between the resource and temporal families with ML confidence of at least 70.

Episode direct-evidence coverage is now:

$$
E_{\text{episode}}
=
\frac{
\text{rows with high-quality direct evidence}
}{
\text{episode rows}
}
$$

A row with five direct flags still contributes only one unit.

---

## 2.5 Episode confidence gate and critical override

The old keep rule allowed any episode with at least one direct-evidence flag to bypass the confidence threshold.

The updated code separates the normal path and the critical override path.

Normal episode handoff requires:

- episode priority at or above the episode threshold; and
- episode confidence at or above the confidence threshold.

The critical override is allowed only when:

- episode impact is at least 80; and
- the episode contains verified high-quality direct evidence.

The following audit fields are exported:

- `episode_confidence_gate_pass`;
- `episode_critical_override_flag`;
- `episode_critical_override_reason`;
- `episode_keep_path`.

Possible keep paths include:

- `priority_and_confidence_gate`;
- `critical_verified_direct_evidence_override`;
- `not_handed_off`.

This makes the episode decision traceable and prevents ordinary evidence flags from bypassing confidence validation.

---

## 2.6 Canonical incident persistence, impact, confidence and priority

Operational incidents now receive their own persistence score:

$$
P_{\text{incident}}
=
100
\left(
0.50S_{\text{longest run}}
+
0.30S_{\text{total anomalous time}}
+
0.20S_{\text{recurrence}}
\right)
$$

where:

- the longest uninterrupted run is normalized at ten seconds;
- total anomalous time is normalized at twenty seconds;
- recurrence is the number of strict episodes, normalized at three episodes.

Incident impact is:

$$
I_{\text{incident}}
=
0.45I_{\max}
+
0.30I_{\text{mean}}
+
0.25P_{\text{incident}}
$$

Incident confidence is:

$$
C_{\text{incident}}
=
0.50C_{\max}
+
0.30C_{\text{mean}}
+
0.10A_{\text{incident}}
+
0.10E_{\text{incident}}
$$

where:

- $A_{\text{incident}}$ is statistical–ML agreement coverage;
- $E_{\text{incident}}$ is high-quality direct-evidence coverage.

The canonical final incident priority is:

$$
R_{\text{incident}}
=
0.55I_{\text{incident}}
+
0.45C_{\text{incident}}
$$

The code now maintains three separate priority fields:

- `peak_row_priority_0_100`;
- `episode_adjusted_priority_0_100`;
- `incident_final_priority_0_100`.

Only `incident_final_priority_0_100` is used for:

- operational incident ranking;
- compact RCA CSV and JSON;
- diverse shortlist ranking;
- dashboard-facing incident priority;
- final severity.

`peak_row_priority_0_100` remains available as supporting one-second severity context.

---

# 3. Priority 1 changes

## 3.1 Fusion-ceiling sensitivity audit

The production confidence ceilings remain:

- statistical evidence ceiling: 0.90;
- ML evidence ceiling: 0.85.

The code now tests nearby combinations:

- statistical: 0.85, 0.90 and 0.95;
- ML: 0.80, 0.85 and 0.90.

For each combination, it exports:

- number of incidents at or above priority 40;
- top-50 incident overlap with the production setting;
- top-50 overlap percentage;
- Spearman incident-rank correlation;
- production-setting indicator.

Output:

`fusion_evidence_ceiling_sensitivity.csv`

This does not automatically tune the ceilings on the same dataset. It checks whether the final incident ranking remains stable around the selected values.

---

## 3.2 Low-tail terminology was corrected

Global P10, IQR and robust MAD remain separate visible statistical methods.

Their relationship is now described as nested severity rather than independent consensus.

New fields are created:

- `low_tail_nested_severity_count`;
- `low_tail_nested_severity_flag`;
- `low_tail_nested_severity_strength_0_1`.

Backward-compatible fields remain available:

- `low_tail_robust_consensus_count`;
- `low_tail_robust_consensus_flag`;
- `low_tail_robust_consensus_strength_0_1`.

The old names are aliases only. Fusion still treats the methods as one low-level family and does not count them as three independent detector families.

---

## 3.3 Fixed 8/10/12 Mbps sensitivity

The 10 Mbps threshold is now documented as an interpretable domain reference, not as a formally optimized threshold.

Two validation outputs are created.

### Row-level sensitivity

`fixed_low_tp_threshold_row_sensitivity.csv`

It reports for 8, 10 and 12 Mbps:

- flagged rows;
- flagged percentage;
- overlap with adaptive low-tail methods;
- adaptive-low-tail recall.

### Downstream sensitivity

`fixed_low_tp_threshold_downstream_sensitivity.csv`

It reports:

- all LTE-DL rows below each threshold;
- percentage below each threshold;
- overlap with P10/IQR/MAD;
- final handoff rows below the threshold;
- final episodes containing a below-threshold row;
- operational incidents containing a below-threshold row.

The sensitivity files are diagnostic only. They do not automatically change the production threshold.

---

## 3.4 HGB naming was made technically accurate

The HGB central models use squared-error regression in log-throughput space. They are not strict mathematical Q50 quantile regressors.

Plot and documentation labels now use:

- `HGB strict-causal temporal central predictor`;
- `HGB resource-conditioned central predictor`.

Internal historical column names containing `_q50` remain unchanged to preserve compatibility with existing outputs and model code.

LSTM retains the Q50 label because it uses Q50 pinball loss.

---

## 3.5 ML feature leakage audit is included in the key review folder

The existing detailed ML leakage audit remains in:

`02_anomaly_detection/02_ml_csv/ml_feature_leakage_audit.csv`

The final code also copies it to:

`04_rca_handoff_final/00_key_review_files/ml_feature_leakage_audit.csv`

This places the causal-feature validation beside the most important final-review outputs.

---

## 3.6 Diverse shortlist selection was strengthened

The shortlist now reserves representation for these paths when available:

1. radio-limited degradation;
2. CA underperformance;
3. temporal local drop;
4. temporal sudden drop;
5. RB-conditioned expected underperformance;
6. radio-conditioned expected underperformance;
7. RB-efficiency underperformance;
8. strict supervised ML-only underperformance.

Remaining slots are filled by canonical incident priority.

To reduce repetition during filling:

- a serving cell is normally limited to two shortlist incidents;
- a session is normally limited to two shortlist incidents;
- the restriction is relaxed only when necessary to reach the target count.

The shortlist target remains 15 incidents.

---

## 3.7 Confirmed bad cells and low-reliability watchlist are separated

The complete ranking remains available.

Two additional dashboard/RCA outputs are created:

- `worst_performing_cells_confirmed.csv`
- `worst_performing_cells_watchlist_low_reliability.csv`

The confirmed file contains HIGH and MEDIUM reliability entities.

The watchlist contains LOW reliability entities that may have insufficient rows or session diversity for a strong ranking conclusion.

The dashboard should always display:

- bad-cell score;
- bad-cell rank;
- ranking reliability.

---

## 3.8 ECI location reliability and uncertainty

Anomalous ECI/cell locations are still based on anomaly-observation coordinates, not assumed physical tower coordinates.

Each location now includes:

- `location_reliability`;
- `location_uncertainty_radius_m`;
- `location_is_tower_coordinate = false`;
- `location_method = anomaly_observation_centroid`.

Reliability is assigned as:

- HIGH: at least ten GPS anomaly rows and P90 spread no greater than 100 m;
- MEDIUM: at least five GPS anomaly rows and P90 spread no greater than 500 m;
- LOW: otherwise.

The GeoJSON properties contain these fields.

The interactive map draws an uncertainty circle rather than implying an exact tower point.

---

## 3.9 Dedicated radio-limited planning queue

Radio-limited anomalies remain part of the main RCA handoff.

A dedicated file is also created:

`rca_radio_limited_planning_incidents.csv`

It is ranked using canonical incident priority and provides a focused queue for investigating:

- coverage;
- dominance;
- interference;
- antenna or tilt configuration;
- neighbor planning;
- mobility and handover context.

---

## 3.10 Operational consolidation sensitivity

The operational incident bridge is tested using:

- time gaps: 3, 5 and 8 seconds;
- distance limits: 30, 50 and 100 meters.

The output reports:

- incident count;
- number of multi-episode incidents;
- top-50 overlap with the production consolidation setting.

Output:

`operational_incident_consolidation_sensitivity.csv`

This allows the production 5-second/50-meter setting to be reviewed for ranking stability.

---

# 4. Priority 2 changes

## 4.1 Machine-readable sampling-gap validation

Notebook 10 now exports:

`sampling_gap_validation_summary.csv`

It includes:

- total rows;
- session count;
- valid gap rows;
- median gap;
- P90 gap;
- P99 gap;
- percentage exactly equal to one second;
- percentage within 1.5 seconds;
- percentage greater than three seconds;
- expected interval;
- PASS or REVIEW result.

---

## 4.2 Explicit pre-anomaly leakage-guard result

The original leakage file may be empty when no forbidden columns are found.

A new one-row summary is exported:

`pre_anomaly_leakage_guard_validation_summary.csv`

It includes:

- input-column count;
- forbidden columns found;
- forbidden columns removed;
- output-column count;
- forbidden columns remaining;
- PASS or FAIL result;
- remaining forbidden column names.

Notebook execution stops if a forbidden post-anomaly feature remains.

---

## 4.3 Q75 operational-decile warning output

The code now identifies prediction deciles that are operationally eligible for anomaly detection:

$$
\text{median predicted Q75} \ge 25\text{ Mbps}
$$

A warning is raised when an eligible decile has absolute Q75 coverage error greater than five percentage points.

Output:

`ml_q75_operational_decile_validation.csv`

It is saved in both:

- the ML CSV folder;
- the key review folder.

---

## 4.4 Run metadata and hashes

Notebook 10 exports:

`preprocessing_run_metadata.json`

Notebook 11 exports:

`final_run_metadata.json`

The metadata includes, where available:

- UTC run timestamp;
- pipeline version;
- whether output cleanup was enabled;
- input-file path;
- input-file SHA-256;
- notebook SHA-256 values;
- row counts;
- column counts;
- session count;
- final fused-row count;
- episode count;
- incident count;
- compact incident count;
- shortlist count;
- generated-file count;
- canonical priority field.

---

## 4.5 Top-20 validation-file manifest

Notebook 11 exports:

`top20_required_validation_files_manifest.csv`

It includes:

- validation order;
- exact relative path;
- absolute path;
- existence flag;
- file size.

This allows the final validation package to be checked automatically after the run.

---

## 4.6 Wide audit table remains internal

The full wide row-level table remains available for debugging, traceability and internal technical review.

It is not used as the RCA team’s primary handoff.

The RCA-facing files remain:

- compact incident CSV;
- compact incident JSON;
- diverse shortlist;
- planning queue;
- bad-cell ranking;
- ECI GeoJSON and maps;
- top anomaly-case plots;
- schema dictionary.

---

# 5. Output folder structure after the update

```text
Throughput_Anomaly_Detection_Outputs/
├── 01_preprocessing_cleaning/
│   ├── lte_dl_feature_table_clean_pre_anomaly.parquet
│   ├── lte_dl_modeling_table.parquet
│   ├── pre_anomaly_feature_table_leakage_guard.csv
│   ├── pre_anomaly_leakage_guard_validation_summary.csv
│   ├── sampling_gap_validation_summary.csv
│   └── preprocessing_run_metadata.json
│
├── 02_anomaly_detection/
│   ├── 01_statistical_csv/
│   ├── 02_ml_csv/
│   └── 03_fusion_csv/
│
├── 03_plots/
│
└── 04_rca_handoff_final/
    ├── 00_key_review_files/
    ├── 01_top_anomaly_case_plots/
    ├── 02_eci_location_maps/
    ├── rca_anomaly_incidents_full_compact.json
    ├── rca_anomaly_incidents_shortlist_diverse.json
    ├── rca_radio_limited_planning_incidents.csv
    ├── worst_performing_cells_confirmed.csv
    └── worst_performing_cells_watchlist_low_reliability.csv
```

---

# 6. Validation performed on the updated code

The delivered notebooks were checked as follows:

- every Python code cell compiles successfully;
- stored outputs and execution counts were cleared;
- the revised episode and incident cell was executed against the supplied 638-column fused-row CSV;
- timestamp-based episode grouping completed successfully;
- direct-evidence coverage became variable rather than constant;
- the revised confidence gate and critical override produced separate decision paths;
- canonical incident metrics were generated successfully;
- the final Priority 0–2 correction cell was runtime-tested using the supplied fused rows, episode data, Q75 calibration file and bad-cell ranking;
- the fusion-ceiling sensitivity code completed successfully.

A complete fresh end-to-end model rerun was not performed in the delivery environment. The updated notebooks must be executed in the project environment in the required order.

---

# 7. Final run and acceptance sequence

1. Place both updated notebooks in the project root.
2. Confirm `Raw_Data/Network_Drive_Test.pkl` is available.
3. Open Notebook 10.
4. Select `Restart Kernel → Run All`.
5. Verify:
   - no execution errors;
   - preprocessing leakage summary is PASS;
   - sampling-gap validation is PASS;
   - pre-anomaly Parquet file exists.
6. Open Notebook 11.
7. Select `Restart Kernel → Run All`.
8. Verify:
   - no execution errors;
   - causal ML leakage audit passes;
   - model metrics and Q75 calibration remain reasonable;
   - direct-evidence coverage is not constant;
   - episode keep paths include normal gate and justified critical override;
   - canonical incident priority is used in all compact outputs;
   - top-20 manifest reports all files as existing;
   - the top anomaly plots show pre-anomaly history and episode boundaries.
9. Archive the two executed notebooks together with the top-20 files below.

---

# 8. Top 20 required files for final project validation and handoff

The following are the exact required output paths, relative to:

`Throughput_Anomaly_Detection_Outputs/`

1. `01_preprocessing_cleaning/lte_dl_feature_table_clean_pre_anomaly.parquet`
2. `01_preprocessing_cleaning/pre_anomaly_leakage_guard_validation_summary.csv`
3. `01_preprocessing_cleaning/sampling_gap_validation_summary.csv`
4. `04_rca_handoff_final/00_key_review_files/statistical_threshold_calibration_report.csv`
5. `04_rca_handoff_final/00_key_review_files/fixed_low_tp_threshold_downstream_sensitivity.csv`
6. `04_rca_handoff_final/00_key_review_files/statistical_low_tail_method_overlap.csv`
7. `02_anomaly_detection/01_statistical_csv/anomaly_method_summary.csv`
8. `02_anomaly_detection/02_ml_csv/ml_feature_leakage_audit.csv`
9. `02_anomaly_detection/02_ml_csv/ml_oof_fold_evaluation_report.csv`
10. `02_anomaly_detection/02_ml_csv/ml_model_evaluation_report.csv`
11. `02_anomaly_detection/02_ml_csv/ml_train_heldout_sequence_fit_metrics.csv`
12. `02_anomaly_detection/02_ml_csv/ml_q75_resource_calibration_by_prediction_decile.csv`
13. `04_rca_handoff_final/00_key_review_files/ml_q75_operational_decile_validation.csv`
14. `04_rca_handoff_final/00_key_review_files/fusion_evidence_ceiling_sensitivity.csv`
15. `02_anomaly_detection/03_fusion_csv/lte_throughput_anomalies_final_fused_row_level.csv`
16. `02_anomaly_detection/03_fusion_csv/lte_throughput_anomaly_episodes_final_rca_handoff.csv`
17. `02_anomaly_detection/03_fusion_csv/lte_throughput_operational_incidents_final_rca_handoff.csv`
18. `04_rca_handoff_final/rca_anomaly_incidents_shortlist_diverse.json`
19. `04_rca_handoff_final/worst_performing_cells_confirmed.csv`
20. `04_rca_handoff_final/02_eci_location_maps/anomalous_eci_approx_locations.geojson`

Also include the two fully executed notebooks:

- `10. LTE_Throughput_PreAnomaly_Final_P0_P2_Updated.ipynb`
- `11. LTE_Throughput_Anomaly_Detection_Final_P0_P2_Updated.ipynb`

And include the full plot folder:

`04_rca_handoff_final/01_top_anomaly_case_plots/`
