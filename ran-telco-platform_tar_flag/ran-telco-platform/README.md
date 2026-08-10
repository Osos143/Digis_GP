# ran-telco-platform

Combines `ran-cleaning-service`, `ran-anomaly-service`, and MongoDB into one
`docker compose` stack. No logic in either service changed as part of this --
the only functional addition is that the anomaly service's 4 JSON outputs are
now also written to MongoDB (see below), everything else runs exactly as
before.

## Layout

```
ran-telco-platform/
├── docker-compose.yml
├── docker/
│   ├── mongo/
│   │   ├── Dockerfile             # wraps official mongo:7, bakes in init script
│   │   └── init/init-indexes.js   # creates the 4 collections + indexes on first boot
│   ├── services/
│   │   ├── Dockerfile             # installs BOTH cleaning + anomaly services into one image
│   │   └── entrypoint.sh          # picks clean / anomaly / both at container start
│   └── kpi-labeling/
│       └── Dockerfile             # installs ran-kpi-labeling-service (interactive)
├── ran-cleaning-service/          # unchanged modular service (see its own README.md)
├── ran-anomaly-service/           # modular service + new MongoDB writes (see its README.md)
├── ran-kpi-labeling-service/      # threshold review + poor/acceptable/good labeling (see its README.md)
├── ran-reason-matching-service/   # RAG-matches root-cause reasons to rca_anomaly_incidents_full_compact anomalies, LLM explains selected matches (see its README.md)
├── netfix-backend/                # NEW: two-phase orchestration API/CLI (Analysis Session, rule-based cause matching) built on top of the above (see its README.md)
├── Raw_Data/                      # put your Network_Drive_Test.pkl here
├── Reasons_Data/                  # put your reasons file here (flat list or taxonomy graph; sample + real graph included)
└── outputs/                       # cleaning + anomaly outputs land here
```

## What's new: MongoDB output

The anomaly service writes exactly 4 JSON files (the cleaning service writes
none -- only CSV/parquet/PNG). Each one is now **also** inserted into a
same-named MongoDB collection, immediately after the existing file write:

| JSON file | MongoDB collection |
|---|---|
| `worst_performing_cells_rca_handoff.json` | `worst_performing_cells_rca_handoff` |
| `worst_performing_pci_rca_handoff.json` | `worst_performing_pci_rca_handoff` |
| `rca_anomaly_incidents_full_compact.json` | `rca_anomaly_incidents_full_compact` |
| `rca_anomaly_incidents_shortlist_diverse.json` | `rca_anomaly_incidents_shortlist_diverse` |

This is purely additive:
- The JSON files are still written to disk exactly as before, same path, same content.
- Every document is tagged with `_run_id` (shared across a whole pipeline run,
  auto-generated as a UTC timestamp if not set) and `_ingested_at`.
- **Non-fatal by design**: if `MONGO_URI` isn't set, `pymongo` isn't
  installed, or the write fails for any reason, it prints a warning and moves
  on -- a Mongo outage can never break a pipeline run or change its file
  outputs. This was verified directly: with `MONGO_URI` unset, `write_json_to_mongo()`
  is a clean no-op; with an unreachable `MONGO_URI`, it logs a warning and
  returns without raising.

The writer lives at `ran-anomaly-service/src/ran_anomaly/mongo_writer.py` and
is called from exactly the 4 sites that already did `json.dump(...)`
(`05_combine_anomaly_cases.py`, `17_episodes_and_incidents.py`) -- one added
line per site, nothing else touched.

## Running it

1. Put your raw drive-test file at `Raw_Data/Network_Drive_Test.pkl` (or edit
   `RAN_CLEAN_INPUT_FILE` in `docker-compose.yml`).

2. Build and run everything:

   ```bash
   docker compose up --build
   ```

   This starts MongoDB, waits for it to be healthy, then runs the services
   container's default command (`both`): `ran-clean` followed by
   `ran-anomaly`, both writing into `./outputs` on your host.

3. Run just one service:

   ```bash
   docker compose run --rm services clean
   docker compose run --rm services anomaly
   ```

4. Inspect what landed in Mongo:

   ```bash
   docker compose exec mongo mongosh ran_telco --eval \
     'db.rca_anomaly_incidents_shortlist_diverse.find().limit(3).pretty()'
   ```

5. Label the anomalies against KPI thresholds (poor/acceptable/good) --
   see `ran-kpi-labeling-service/README.md` for full details. This is a
   third, independent service that reads/writes MongoDB only (it never
   touches the file outputs from steps 2-4). It's interactive by default
   (asks whether to change any threshold), so run it with `-it`:

   ```bash
   docker compose run --rm -it kpi-label
   # or, if your compose version gates it behind its profile:
   docker compose --profile tools run --rm -it kpi-label

   # non-interactive, only the latest run:
   docker compose run --rm -it kpi-label --non-interactive --latest-run
   ```

6. Match root-cause reasons to anomalies -- see
   `ran-reason-matching-service/README.md` for full details. This is a
   fourth, independent service, split into two mechanisms:
   - **Matching is RAG (retrieval), not an LLM decision**: reasons and
     anomaly evidence are embedded with a local Ollama embedding model, and
     the closest reason by cosine similarity is the match -- deterministic,
     fast, no LLM call involved. Every anomaly gets matched automatically.
   - **Explaining is interactive and user-driven**: after matching, the
     matched anomalies are listed in the terminal and you're asked which
     one(s) to explain. Only your picks get a single local LLM call to
     write up why the evidence supports the match -- nothing is explained
     automatically.

   Both steps run against **local models via Ollama by default -- no API
   key needed**:

   ```bash
   docker compose up -d ollama
   docker compose exec ollama ollama pull nomic-embed-text   # embeddings, first time only
   docker compose exec ollama ollama pull llama3.1           # explanations, first time only

   docker compose run --rm reason-match upload-reasons \
     --file /data/reasons/throughput_degradation_reasoning_graph.json
   # -it because the explain step is interactive (asks which anomaly to explain):
   docker compose run --rm -it reason-match run --latest-run \
     --export-json /data/outputs/anomalies_with_reasons.json
   # or, if your compose version gates it behind its profile:
   docker compose --profile tools run --rm -it reason-match run --latest-run
   ```

   To use Claude for the explanation step instead of a local model (matching
   stays local either way), set `ANTHROPIC_API_KEY` in your `.env` and add
   `--provider anthropic` to the `run` command. To skip the interactive
   explain step entirely and only get the RAG match, add `--no-explain`.

7. **Or, skip steps 5-6 and use the unified NetFix backend instead** -- see
   `netfix-backend/README.md`. It wraps cleaning, anomaly detection,
   threshold-based labeling, and cause matching + explanation into one
   two-phase API/CLI built around a single Analysis Session, with cause
   matching done by deterministic rules rather than RAG:

   ```bash
   docker compose up -d mongo ollama
   docker compose exec ollama ollama pull llama3.1

   docker compose up -d netfix-backend
   # http://localhost:8000/docs
   ```

   This is an additional entry point, not a replacement -- `services`,
   `kpi-label`, and `reason-match` remain independently usable exactly as
   described in steps 2-6 above.

8. Tear down (keeps the named `mongo-data` volume, so Mongo data persists):

   ```bash
   docker compose down
   ```

   Add `-v` to also wipe Mongo's data volume.

## Configuration

All via environment variables in `docker-compose.yml`'s `services:` block:

| Variable | Default | Meaning |
|---|---|---|
| `RAN_CLEAN_INPUT_FILE` | `/data/raw/Network_Drive_Test.pkl` | raw pickle inside the container (mounted from `./Raw_Data`) |
| `RAN_CLEAN_OUTPUT_DIR` | `/data/outputs` | cleaning output root inside the container |
| `RAN_ANOMALY_OUTPUT_DIR` | `/data/outputs` | anomaly output root inside the container (must match the cleaning one) |
| `MONGO_URI` | `mongodb://mongo:27017` | Mongo connection string; the service name `mongo` resolves via Docker's internal network |
| `MONGO_DB` | `ran_telco` | database name |
| `LLM_PROVIDER` | `ollama` | `reason-match run`'s explanation-step provider: `ollama` (local, default) or `anthropic` |
| `LLM_MODEL` | `llama3.1` | explanation model for whichever provider is selected |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model used for RAG matching (always local, regardless of `LLM_PROVIDER`) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama server address; the service name `ollama` resolves via Docker's internal network |
| `ANTHROPIC_API_KEY` | *(none)* | only required when `LLM_PROVIDER=anthropic` / `--provider anthropic` |

Both host folders `./Raw_Data` (read-only) and `./outputs` (read-write) are
bind-mounted, so cleaning/anomaly outputs are visible on your host machine
immediately, not locked inside the container.

## Running without Docker at all

Nothing here is Docker-only -- both services still work exactly as documented
in their own READMEs, standalone, with `pip install -e .`. MongoDB is opt-in
via `--mongo-uri`:

```bash
ran-clean   --input Raw_Data/Network_Drive_Test.pkl --output-dir outputs
ran-anomaly --output-dir outputs --mongo-uri mongodb://localhost:27017
```

Omit `--mongo-uri` (and don't set `MONGO_URI`) to skip MongoDB entirely --
file outputs are identical either way.

`ran-kpi-labeling-service` and `ran-reason-matching-service` are Mongo-only
tools (no `--mongo-uri` flag needed if `$MONGO_URI` is set):

```bash
ran-kpi-label --mongo-uri mongodb://localhost:27017

ran-reason-match upload-reasons --file Reasons_Data/throughput_degradation_reasoning_graph.json
ran-reason-match run --latest-run   # local models via Ollama by default -- run `ollama serve` and pull both models first
```
