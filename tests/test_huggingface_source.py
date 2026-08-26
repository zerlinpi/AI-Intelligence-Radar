from datetime import datetime, timezone

from app.sources import huggingface


class FakeResponse:
    def __init__(self, *, payload=None, text="", status_code=200):
        self._payload = payload
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _model(model_id, pipeline_tag, library_name, tags, downloads=100, likes=2):
    return {
        "modelId": model_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "downloads": downloads,
        "likes": likes,
        "pipeline_tag": pipeline_tag,
        "library_name": library_name,
        "tags": tags,
    }


def test_model_card_can_surface_real_hardware_use_and_reject_generic_model(monkeypatch):
    generic = _model(
        "org/generic-chat-model",
        "text-generation",
        "transformers",
        ["llm", "chat", "text-generation"],
        downloads=5000,
        likes=20,
    )
    hardware = _model(
        "org/edge-wearable-audio",
        "audio-classification",
        "tflite",
        ["audio", "edge"],
        downloads=120,
        likes=4,
    )

    def fake_get(url, **kwargs):
        if url == huggingface.API:
            return FakeResponse(payload=[generic, hardware])
        if url.endswith("/org/generic-chat-model/raw/main/README.md"):
            return FakeResponse(
                text="# Generic Chat Model\nGeneral-purpose text generation and chatbot research model."
            )
        if url.endswith("/org/edge-wearable-audio/raw/main/README.md"):
            return FakeResponse(
                text=(
                    "---\nlanguage: en\n---\n# Edge Wearable Audio\n"
                    "On-device keyword spotting and audio classification for a low-power wearable "
                    "consumer device using embedded sensors and a TFLite runtime. Suitable for "
                    "fitness and personal safety hardware prototypes."
                )
            )
        return FakeResponse(status_code=404)

    monkeypatch.setattr(huggingface.requests, "get", fake_get)

    results = huggingface.HuggingFaceCollector().collect(limit=10)
    titles = [item["title"] for item in results]

    assert "org/edge-wearable-audio" in titles
    assert "org/generic-chat-model" not in titles

    item = next(row for row in results if row["title"] == "org/edge-wearable-audio")
    assert "MODEL_CARD:" in item["description"]
    assert "On-device keyword spotting" in item["description"]
    assert item["metrics"]["model_card_evidence"] is True
    assert item["metrics"]["model_card_chars"] > 100
    assert item["metrics"]["report_eligible"] is True
    assert "硬件开发" in item["metrics"]["priority_tags"]


def test_clean_model_card_removes_front_matter_and_code():
    cleaned = huggingface._clean_model_card(
        "---\nlanguage: en\nlicense: mit\n---\n"
        "# Model\nUse [this model](https://example.com) on-device.\n"
        "```python\nprint('noise')\n```"
    )

    assert "language: en" not in cleaned
    assert "print('noise')" not in cleaned
    assert "this model" in cleaned
    assert "on-device" in cleaned
