# ran-rca-explanation-service

A standalone service, independent of the rest of `ran-telco-platform` --
no shared code, no shared dependencies beyond common libraries (pydantic,
LangChain). Its one job: given a JSON document describing an
already-analyzed anomaly (its evidence/KPIs, its matched root cause(s), and
optionally solution(s) someone/something else already proposed), generate a
polished, professional explanation of it -- written the way a senior
RAN/RF optimization engineer would explain it to a colleague or
stakeholder.

**This service does not detect anomalies, does not decide root causes, and
does not invent solutions.** It only explains what it's given, grounded
strictly in the evidence in the input JSON. The system prompt explicitly
forbids stating a KPI value, cause, or recommendation that isn't present in
the input.

## Which Ollama model, and why

**Default: `qwen3:14b`.**

This needed fresh consideration rather than reusing a default from
elsewhere, because the task profile is genuinely different from this
platform's other LLM steps (which produce a short, structured verdict).
Here the deliverable is a full, polished, multi-paragraph professional
document, and the input is technical, structured, numeric evidence that
must be represented faithfully -- both of those push harder on a model's
instruction-following and long-context-coherence than a one-line
classification does.

I checked current (2026) comparative data rather than relying purely on
older training knowledge, since the local-model landscape moves fast. What
that comparison showed, specifically relevant to this task:

- **Instruction-following / structured-output consistency**: Qwen3 14B
  scores meaningfully higher than Llama 3.1/3 8B on MMLU (74.8 vs 66.6) and
  is specifically noted for holding and applying context correctly across
  multiple paragraphs -- exactly the failure mode that matters here (a
  model that loses track of which KPI value belongs to which claim
  partway through a report is actively harmful for this use case, not just
  lower quality).
- **Faithfulness/grounding**: the highest-scoring option for strict
  context-grounding with minimal hallucination in 2026 comparisons is
  Llama 3.3 70B -- but at 70B it needs workstation-class hardware (dual-GPU
  or a high-memory Mac), which isn't a reasonable default for "a local LLM
  that works via Ollama" on typical developer hardware. Qwen3 14B is the
  best-quality option that stays in a realistically runnable range
  (fits at 10-12GB VRAM, Q4 quantization).
- **Persona/tone reliability**: writing consistently "as a senior engineer"
  across an entire report (not just answering a single question) is an
  instruction-following-heavy task, which is Qwen3 14B's specific strength
  relative to same-or-smaller Llama models per current comparisons.
- Works out of the box with `langchain-ollama`'s `ChatOllama` -- no special
  configuration beyond a standard `ollama pull qwen3:14b`.

**Practical alternatives, explicitly supported via `--model`:**

| Model | When to use it |
|---|---|
| `qwen3:14b` (default) | Best balance of quality and hardware realism for this specific task. Needs ~10-12GB VRAM at Q4. |
| `llama3.1:8b` | Hardware-constrained fallback (≤8GB VRAM, or CPU-only). Already used elsewhere in this platform, well-tested, reliable instruction-following -- just measurably weaker at sustaining a long, technically precise, multi-paragraph explanation than Qwen3 14B. |
| `llama3.3:70b` | If you have workstation-class hardware (dual-GPU / high-memory Mac Studio) and want the strongest available grounding fidelity for a report that goes to real network engineers -- current data specifically credits it as the strongest option for synthesizing answers from provided context without inventing facts. |

Switch with `--model llama3.1:8b` (or any other) / `$LLM_MODEL` -- nothing
else about the service changes.

## Input contract

Three shapes are accepted, auto-detected (see `loader.py`'s docstring for
the full detail):

1. **Single anomaly** (see `sample_input.json` in this repo for a full example):
    ```json
    {
      "anomaly_id": "INC-0017",
      "anomaly": { "...": "any KPI/evidence fields, any nesting..." },
      "reasons": [ {"title": "Low RSRP", "category": "Coverage", "description": "..."} ],
      "solutions": [ {"title": "...", "description": "...", "priority": "High"} ]
    }
    ```
   Only `anomaly` is required; `reasons`/`solutions` default to empty
   (the report will note no root cause/solution was available rather than
   inventing one).

2. **A JSON array** of objects in shape 1, for batch processing.

3. **A full netfix-backend Analysis Session document** (or anything with the
   same `anomalies` + `matched_causes` shape) -- every anomaly in it becomes
   one explanation automatically, using its own matched causes. Sessions
   have no `solutions` field (this platform's architecture deliberately
   excludes solution retrieval), so those come back empty unless you add
   them to the JSON yourself first.

## Output

A `RcaExplanationReport`: `executive_summary`, `root_cause_narrative`,
`supporting_evidence` (list), `recommended_actions` (list, only populated
if solutions were given). Rendered to markdown by default, or `--format
json` for the raw structured object.

## Usage

```bash
pip install -e ".[cloud]"   # cloud extra optional, only needed for --provider anthropic

ollama pull qwen3:14b

ran-rca-explain --input sample_input.json
ran-rca-explain --input sample_input.json --format json
ran-rca-explain --input netfix_session.json --output-dir reports/
ran-rca-explain --input netfix_session.json --anomaly-id INC-0017

# lighter model for constrained hardware
ran-rca-explain --input sample_input.json --model llama3.1:8b

# Claude instead of a local model
ANTHROPIC_API_KEY=sk-ant-... ran-rca-explain --input sample_input.json --provider anthropic
```

### API

```bash
uvicorn ran_rca_explanation.api:app --reload
```
```bash
curl -X POST localhost:8000/explain -H "Content-Type: application/json" \
  -d '{"anomaly_id": "INC-0017", "anomaly": {"radio_kpis": {"rsrp_median_dbm": -118.4}}, "reasons": [{"title": "Low RSRP", "category": "Coverage"}]}'
```
`POST /explain` takes `{"anomaly_id"?, "anomaly", "reasons"?, "solutions"?}` and returns the `RcaExplanationReport` JSON directly.

### Docker

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen3:14b
docker compose up -d rca-explain
# http://localhost:8010/docs

docker compose run --rm rca-explain ran-rca-explain --input /data/sample_input.json
```

## Project layout

```
ran-rca-explanation-service/
├── pyproject.toml
├── README.md
├── sample_input.json
├── docker/Dockerfile
├── docker-compose.yml
└── src/ran_rca_explanation/
    ├── schema.py       # ExplanationRequest (input) + RcaExplanationReport (output)
    ├── loader.py        # auto-detects single/batch/session input shape
    ├── formatter.py      # flattens evidence + reasons + solutions into prompt text
    ├── explainer.py       # the LLM call: senior-RAN-engineer prompt, Ollama-first
    ├── renderer.py         # structured report -> markdown
    ├── cli.py               # ran-rca-explain
    └── api.py                # FastAPI app
```
