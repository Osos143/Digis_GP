RCA HANDOFF — START HERE

1. rca_anomaly_incidents_shortlist_diverse.json
   Primary presentation/review set: diverse high-priority incidents across anomaly cases.
2. rca_anomaly_incidents_full_compact.json
   Full compact RCA-ready incident handoff. Strict ML-only incidents are marked requires_human_review=true.
3. worst_performing_cells_rca_handoff.json
   Serving-cell ranking using throughput, anomaly/gap evidence, CQI, MCS, BLER, SINR, RSRQ and RSRP.
4. worst_performing_pci_rca_handoff.json
   Secondary PCI-only view. PCI reuse means this is not as reliable as ECI/EARFCN+PCI cell identity.
5. 01_top_anomaly_case_plots/
   Top examples per standardized anomaly case with actual throughput, expected references and explicit gap/drop annotation.

LSTM-Q50 and Isolation Forest are model-selection/context validators only and are deliberately excluded from the compact RCA JSON.
