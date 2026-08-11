from ran_rca_explanation.explainer import RcaExplainerLLM
from ran_rca_explanation.schema import ExplanationRequest


class DummyChat:
    def invoke(self, prompt):
        return "The anomaly is consistent with interference-driven degradation. The evidence points to a localized coverage issue that reduced throughput and created a visible service impact."


def test_explainer_returns_freeform_explanation_text():
    explainer = RcaExplainerLLM.__new__(RcaExplainerLLM)
    explainer._chat = DummyChat()
    explainer.provider = "ollama"

    request = ExplanationRequest(
        anomaly_id="INC-001",
        anomaly={"incident_id": "INC-001", "kpi": 42},
        reasons=[{"title": "Interference", "description": "Neighboring cells were overpowering the serving cell"}],
        solutions=[],
    )

    report = explainer.explain(request)

    assert report.explanation == (
        "The anomaly is consistent with interference-driven degradation. "
        "The evidence points to a localized coverage issue that reduced throughput and created a visible service impact."
    )
