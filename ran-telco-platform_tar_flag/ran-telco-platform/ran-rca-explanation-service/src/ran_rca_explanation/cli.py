"""
Command-line entry point: ran-rca-explain

    ran-rca-explain --input anomaly.json
    ran-rca-explain --input session.json --output-dir reports/ --format markdown
    ran-rca-explain --input anomaly.json --anomaly-id INC-0017   # only this one, if the file is a batch/session
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ran_rca_explanation.explainer import DEFAULT_MODELS, DEFAULT_OLLAMA_BASE_URL, RcaExplainerLLM
from ran_rca_explanation.loader import load_requests
from ran_rca_explanation.renderer import render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ran-rca-explain",
        description="Generate a professional, senior-RAN-engineer-style explanation for one or more "
                    "already-analyzed anomalies.",
    )
    parser.add_argument("--input", required=True, help="Path to the input JSON (see README for accepted shapes).")
    parser.add_argument("--anomaly-id", default=None, help="Only explain this one anomaly, if --input is a batch/session file.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                         help="Output format. Default: markdown.")
    parser.add_argument("--output-dir", default=None,
                         help="Write one file per anomaly here instead of printing to stdout.")

    parser.add_argument("--provider", choices=list(DEFAULT_MODELS), default=os.environ.get("LLM_PROVIDER", "ollama"),
                         help="Defaults to $LLM_PROVIDER, or 'ollama' (local, no API key).")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL"),
                         help=f"Defaults to $LLM_MODEL, or the provider's default "
                              f"({', '.join(f'{k}: {v}' for k, v in DEFAULT_MODELS.items())}).")
    parser.add_argument("--ollama-base-url", default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set -- required when --provider=anthropic.", file=sys.stderr)
        return 1

    requests = load_requests(args.input)
    if args.anomaly_id:
        requests = [r for r in requests if r.anomaly_id == args.anomaly_id]
        if not requests:
            print(f"ERROR: anomaly_id '{args.anomaly_id}' not found in {args.input}.", file=sys.stderr)
            return 1

    print(f"Loaded {len(requests)} anomaly(ies) from {args.input}.", file=sys.stderr)

    explainer = RcaExplainerLLM(provider=args.provider, model=args.model, base_url=args.ollama_base_url)
    print(f"Model: {explainer.model} (provider={args.provider})", file=sys.stderr)

    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    for request in requests:
        print(f"Explaining {request.anomaly_id}...", file=sys.stderr)
        report = explainer.explain(request)

        if args.format == "markdown":
            output = render_markdown(request, report)
            ext = "md"
        else:
            output = json.dumps(report.model_dump(), indent=2)
            ext = "json"

        if args.output_dir:
            out_path = Path(args.output_dir) / f"{request.anomaly_id}.{ext}"
            out_path.write_text(output, encoding="utf-8")
            print(f"  -> {out_path}", file=sys.stderr)
        else:
            print(output)
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
