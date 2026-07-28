RCA HANDOFF — START HERE

1. rca_anomaly_incidents_full_compact.json
   Full compact RCA-ready incident payload. incident_final_priority_0_100 is the canonical ranking field.
2. rca_anomaly_incidents_shortlist_diverse.json
   Diverse high-value examples for review and presentation.
3. 00_key_review_files/rca_handoff_integrity_validation.csv
   Confirms JSON/CSV counts, IDs, required sections, and canonical priorities.
4. rca_radio_limited_planning_incidents.csv
   Coverage/planning-focused queue for radio-limited degradation.
5. worst_performing_cells_confirmed.csv
   Confirmed bad-cell ranking. Use rank_reliability on the dashboard.
6. 02_eci_location_maps/
   Approximate anomaly-observation centroids with uncertainty. These are not confirmed tower coordinates.
7. 01_top_anomaly_case_plots/
   Pre-anomaly history, shaded episode, expected references, central predictors,
   canonical incident priority, and peak one-second row priority.

LSTM-Q50 and Isolation Forest are validation/context methods and are excluded from the compact RCA decision payload.
RB-efficiency remains available in statistical_evidence.rb_efficiency and dominant_statistical_type; no separate RCA dashboard view is generated.
