"""
The only LLM call in this service. Takes one ExplanationRequest (an
anomaly's evidence + its matched reason(s) + any given solutions) and
produces one RcaExplanationReport -- a polished, professional explanation
written in the voice of a senior RAN/RF optimization engineer.

This service does not decide anything -- the root cause was already matched
upstream, and any solutions were already proposed upstream (or not, in
which case none are mentioned). The LLM's only job is to explain, in expert
but readable language, why the given evidence supports the given reason(s),
and to walk through the given solution(s) if any were supplied. It is
explicitly instructed never to invent KPI values, causes, or
recommendations beyond what's in the input -- see the system prompt below.

Model: defaults to a local model via Ollama (`qwen3:14b`) -- see this
package's README for the full reasoning behind that specific choice, and
the lighter/heavier alternatives documented there for different hardware.
Anthropic (Claude) is available as an opt-in via `--provider anthropic` for
anyone who'd rather not run a local model, needs the `cloud` extra.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from ran_rca_explanation.formatter import build_prompt_context
from ran_rca_explanation.schema import ExplanationRequest, RcaExplanationReport

DEFAULT_MODELS = {
    "ollama": "qwen3:14b",
    "anthropic": "claude-sonnet-5",
}
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

_SYSTEM_PROMPT = (
    "You are a senior RAN (Radio Access Network) / RF optimization engineer with over a decade of "
    "field experience diagnosing LTE and 5G throughput, coverage, interference, and capacity issues. "
    "You have been given one detected network anomaly: its raw KPI/evidence data, the root cause(s) "
    "that have ALREADY been determined for it by an upstream analysis system, and (optionally) "
    "solution(s) that have ALREADY been proposed by that same upstream process.\n\n"
    "Your job is only to EXPLAIN this anomaly professionally, the way you would to a colleague or a "
    "non-specialist stakeholder who trusts your expertise -- not to re-diagnose it, not to question the "
    "given root cause(s), and not to invent new solutions. Ground every claim strictly in the evidence "
    "provided below. Never state a specific KPI value, threshold, or fact that is not present in the "
    "evidence. If solutions were provided, explain them in your own words and why they address the root "
    "cause; if none were provided, do not propose any -- simply omit that part of your explanation.\n\n"
    "Write with the technical precision and calm authority of an experienced engineer, but keep it "
    "readable -- avoid unnecessary jargon, and when you do use a technical term, its meaning should be "
    "clear from context."
)

_HUMAN_PROMPT = (
    "Anomaly ID: {anomaly_id}\n\n"
    "Evidence (raw KPI/anomaly data):\n{evidence}\n\n"
    "Root cause(s) already determined:\n{reasons}\n\n"
    "Solution(s) already proposed (explain these if present; do not invent others if absent):\n{solutions}\n\n"
    "Write the professional explanation."
)

_PROMPT = ChatPromptTemplate.from_messages([("system", _SYSTEM_PROMPT), ("human", _HUMAN_PROMPT)])


class RcaExplainerLLM:
    def __init__(
        self,
        provider: str = "ollama",
        model: Optional[str] = "qwen3:14b",
        temperature: float = 0.3,
        max_tokens: int = 1200,
        base_url: Optional[str] = None,
    ):
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"Unknown provider '{provider}'. Use one of: {', '.join(DEFAULT_MODELS)}.")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]

        if provider == "ollama":
            from langchain_ollama import ChatOllama
            self._chat = ChatOllama(
                model=self.model, temperature=temperature, num_predict=max_tokens,
                base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
            )
        else:
            from langchain_anthropic import ChatAnthropic
            self._chat = ChatAnthropic(model=self.model, temperature=temperature, max_tokens=max_tokens)

    def _structured(self, schema):
        if self.provider == "ollama":
            return self._chat.with_structured_output(schema, method="json_schema")
        return self._chat.with_structured_output(schema)

    def explain(self, request: ExplanationRequest) -> RcaExplanationReport:
        context = build_prompt_context(request)
        chain = _PROMPT | self._structured(RcaExplanationReport)
        return chain.invoke(context)
