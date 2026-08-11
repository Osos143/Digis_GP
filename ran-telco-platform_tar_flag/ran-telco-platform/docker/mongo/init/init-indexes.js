// Runs once, automatically, the first time the Mongo container starts with an
// empty data directory. Creates the ran_telco database (implicitly, via the
// first write) and useful indexes on the four collections the anomaly service
// writes to (see ran_anomaly/mongo_writer.py and stages 05 and 17).

db = db.getSiblingDB("ran_telco");

db.createCollection("worst_performing_cells_rca_handoff");
db.createCollection("worst_performing_pci_rca_handoff");
db.createCollection("rca_anomaly_incidents_full_compact");
db.createCollection("rca_anomaly_incidents_shortlist_diverse");

// Every document written by mongo_writer.py is tagged with _run_id and
// _ingested_at -- index both so you can query/filter by pipeline run.
["worst_performing_cells_rca_handoff",
 "worst_performing_pci_rca_handoff",
 "rca_anomaly_incidents_full_compact",
 "rca_anomaly_incidents_shortlist_diverse"].forEach(function (name) {
  db[name].createIndex({ "_run_id": 1 });
  db[name].createIndex({ "_ingested_at": 1 });
});

// Used by ran-reason-matching-service: uploaded root-cause reason
// definitions (+ their LLM-generated digest), keyed uniquely by reason_id.
db.createCollection("rca_reasons");
db.rca_reasons.createIndex({ "reason_id": 1 }, { unique: true });

print("ran_telco database initialized: collections + indexes created.");
