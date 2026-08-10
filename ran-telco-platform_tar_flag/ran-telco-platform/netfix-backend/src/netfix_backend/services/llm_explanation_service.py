"""
LLMExplanationService: Phase 2's last step. This is the ONLY place an LLM is
called anywhere in the NetFix backend.

Reuses ran-reason-matching-service's `explainer.py` for the generic,
matching-method-agnostic pieces (the `Explanation` Pydantic schema, the
provider/model setup for Ollama-local-by-default with Claude as an opt-in) --
but NOT its prompt template, which explicitly describes "a retrieval system
... based on embedding similarity". That wording would be actively wrong
here: NetFix's cause matching is rule-based (deterministic KPI-threshold
comparisons via CauseMatchingService), not RAG. Telling the explanation LLM
the match came from embedding similarity when it actually came from an
explicit rule would risk it fabricating similarity-flavored reasoning that
doesn't correspond to what actually happened. Hence this module's own
prompt, describing the real mechanism accurately.

If an anomaly has multiple matched causes, one explanation call covers all
of them together (an engineer reading about one anomaly wants one coherent
write-up, not N separate paragraphs) rather than one call per matched
reason.
"""

from __future__ import annotations

import importlib
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate

DEFAULT_MODELS: dict[str, str] = {"ollama": "llama3.1", "anthropic": "claude-sonnet-4-20250514"}
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
_evidence_text: Any = None

try:
    mod = importlib.import_module("ran_reason_matching.explainer")
    DEFAULT_MODELS = mod.DEFAULT_MODELS
    DEFAULT_OLLAMA_BASE_URL = mod.DEFAULT_OLLAMA_BASE_URL
except ModuleNotFoundError:
    pass

_EXPLAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a RAN (Radio Access Network) root-cause-analysis expert. A rule-based system has already "
     "determined which root cause(s) apply to a detected throughput anomaly, by comparing the anomaly's KPI "
     "values against user-configured poor/acceptable/good thresholds -- each matched cause fired because a "
     "specific KPI crossed its defined 'poor' threshold. Your only job is to EXPLAIN this deterministic match "
     "in plain language for a RAN engineer -- do not question, re-evaluate, or propose a different cause, and "
     "do not invent KPI values that aren't present in the evidence given."),
    ("human",
     "Anomaly evidence:\n{evidence}\n\n"
     "Matched cause(s): {reason_title} (categor{y_or_ies}: {reason_category})\n"
     "Why each matched (from the threshold rule engine):\n{reason_description}\n\n"
     "Explain why this evidence supports these matched cause(s)."),
])


class RuleBasedExplainerLLM:
    """Same provider abstraction as ran_reason_matching.explainer.ReasonExplainerLLM
    (local Ollama by default, Anthropic optional), with a prompt that
    accurately describes rule-based matching instead of RAG."""

    def __init__(
        self,
        provider: str = "ollama",
        model: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: int = 1024,
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

    def explain(self, evidence_text: str, combined_reason: dict[str, Any]) -> Any:
        try:
            from ran_reason_matching.explainer import Explanation
        except ModuleNotFoundError:
            raise RuntimeError("ran_reason_matching package is not installed. Phase 2 (LLM explanations) is unavailable.")
        chain = _EXPLAIN_PROMPT | self._structured(Explanation)
        return chain.invoke({
            "evidence": evidence_text,
            "reason_title": combined_reason["title"],
            "reason_category": combined_reason.get("category", "n/a"),
            "reason_description": combined_reason.get("description", ""),
            "y_or_ies": "ies" if "+" in combined_reason.get("reason_id", "") else "y",
        })


class LLMExplanationService:
    def __init__(self, explainer: RuleBasedExplainerLLM):
        self.explainer = explainer

    def explain(self, anomaly_doc: dict[str, Any], matched_causes: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            from ran_reason_matching.evidence import build_evidence, evidence_to_text
        except ModuleNotFoundError:
            raise RuntimeError("ran_reason_matching package is not installed. Phase 2 (LLM explanations) is unavailable.")

        if not matched_causes:
            return {
                "text": "No root cause could be matched for this anomaly with the current thresholds -- "
                        "no explanation was generated.",
                "key_evidence": [],
                "model": None,
            }

        evidence_text = evidence_to_text(build_evidence(anomaly_doc))
        combined_reason = {
            "reason_id": "+".join(c["reason_id"] for c in matched_causes),
            "title": " and ".join(c["title"] for c in matched_causes),
            "category": ", ".join(sorted({c["category"] for c in matched_causes if c.get("category")})),
            "description": "\n".join(f"- {c['title']}: {c.get('description', '')}" for c in matched_causes),
        }
        explanation = self.explainer.explain(evidence_text, combined_reason)
        return {
            "text": explanation.explanation,
            "key_evidence": explanation.key_evidence,
            "model": self.explainer.model,
        }
