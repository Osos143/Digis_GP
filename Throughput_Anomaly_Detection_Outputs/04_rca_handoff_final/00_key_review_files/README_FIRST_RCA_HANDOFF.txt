RCA HANDOFF — START HERE

1. rca_anomaly_incidents_shortlist_diverse.json
   Diverse, high-priority incidents across anomaly cases. ML-only incidents require supervision.
2. rca_anomaly_incidents_full_compact.json
   Full compact RCA-ready incident handoff with MCS, CQI, BLER, radio/planning relevance, and map coordinates.
3. worst_performing_cells_rca_handoff.json / worst_performing_pci_rca_handoff.json
   Cell/PCI ranking. ECI or EARFCN+PCI is preferred because PCI can be reused.
4. 02_eci_location_maps/
   Approximate anomaly-observation locations in CSV/GeoJSON/HTML/static PNG. These are not guaranteed tower coordinates.
5. 01_top_anomaly_case_plots/
   Pre-anomaly history, selected-row line, shaded episode, and split expected/predictive panels.

LSTM-Q50 and Isolation Forest remain validation/context methods and are excluded from compact RCA JSON.
