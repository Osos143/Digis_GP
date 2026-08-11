"""
The only LLM call in this service. Takes the full reason-matching result
JSON and produces a professional, insightful explanation that goes beyond
just restating the data -- the LLM is instructed to interpret KPI values,
explain RF engineering implications, connect symptoms to root causes with
real-world reasoning, and provide actionable context for solutions.

Model: defaults to a local model via Ollama (`qwen3:14b`).
Anthropic (Claude) is available as an opt-in via `--provider anthropic`.
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
    "You are a senior RAN (Radio Access Network) / RF optimization engineer with 15+ years of "
    "hands-on field experience diagnosing LTE and 5G performance issues across hundreds of cell sites.\n\n"

    "You have just received the output of an automated Root Cause Analysis pipeline. Your job is NOT "
    "to simply repeat or summarize what the JSON says — the user can already read the raw data. "
    "Instead, you must ADD VALUE by providing:\n\n"

    "1. **Engineering Interpretation**: Explain what the KPI values actually MEAN in practice. "
    "For example, if RSRP is -110 dBm, explain that this indicates the UE is at the cell edge with "
    "very weak signal, likely experiencing frequent re-selections. If SINR is 2 dB, explain this "
    "means heavy inter-cell interference is degrading the link budget. Don't just say 'RSRP is -110' "
    "— explain WHY that value is problematic and what it tells you about the RF environment.\n\n"

    "2. **Cause-Effect Chain**: Walk through the logical chain from observed symptoms to root cause. "
    "Explain HOW poor coverage leads to throughput degradation, or HOW interference causes BLER "
    "increases which force the scheduler to use lower MCS, reducing capacity. Show the engineering "
    "reasoning, not just the conclusion.\n\n"

    "3. **Real-World Impact**: Describe what the end user actually experiences — dropped video calls, "
    "buffering during streaming, failed file downloads, slow web browsing. Make it concrete.\n\n"

    "4. **Solution Context**: For each recommended action, explain WHY it would fix the problem "
    "from an RF engineering perspective. If the recommendation is to adjust antenna tilt, explain "
    "how that changes the coverage footprint and reduces interference to neighbors. If it's to "
    "add a carrier, explain how that offloads traffic and improves per-user throughput.\n\n"

    "5. **Severity Assessment**: Based on the KPI values, give your professional assessment of "
    "how urgent this issue is and what could happen if it's left unaddressed.\n\n"

    "Write in a natural, professional tone — like you're briefing your network director or a "
    "customer's CTO. Use technical terms where appropriate but always explain their implications. "
    "DO NOT output JSON, bullet lists of raw field values, or generic template text. "
    "Write a flowing, insightful narrative that demonstrates genuine RF engineering expertise."
)

_HUMAN_PROMPT = (
    "Anomaly ID: {anomaly_id}\n\n"
    "Below is the automated RCA pipeline output for this incident. Read it thoroughly, then write "
    "your expert analysis. Remember: don't just restate these values — INTERPRET them, explain the "
    "RF engineering implications, and provide insight that goes beyond what the raw data shows.\n\n"
    "--- DIAGNOSIS ---\n{diagnosis}\n\n"
    "--- KEY KPI MEASUREMENTS ---\n{kpi_evidence}\n\n"
    "--- RECOMMENDED ACTIONS & STANDARDS ---\n{solutions}\n\n"
    "--- SUPPORTING EVIDENCE ---\n{supporting_evidence}\n\n"
    "Now write your Senior RF Engineer analysis. Focus on:\n"
    "- What do these KPI values tell you about the RF environment and user experience?\n"
    "- Why does the evidence confirm this specific root cause (not just 'the values are abnormal')?\n"
    "- How would each recommended action address the underlying problem?\n"
    "- How urgent is this issue based on the severity of the KPI degradation?"
)

_PROMPT = ChatPromptTemplate.from_messages([("system", _SYSTEM_PROMPT), ("human", _HUMAN_PROMPT)])


class RcaExplainerLLM:
    def __init__(
        self,
        provider: str = "ollama",
        model: Optional[str] = "qwen3:14b",
        temperature: float = 0.5,
        max_tokens: int = 2000,
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

    def explain(self, request: ExplanationRequest) -> RcaExplanationReport:
        context = build_prompt_context(request)
        chain = _PROMPT | self._chat
        result = chain.invoke(context)

        if hasattr(result, "content"):
            text = result.content
        else:
            text = str(result)

        return RcaExplanationReport(explanation=text)
