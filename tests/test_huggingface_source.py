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
        ["llm", "chat", "text-generation", "license:apache-2.0"],
        downloads=5000,
        likes=20,
    )
    hardware = _model(
        "org/edge-wearable-audio",
        "audio-classification",
        "tflite",
        ["audio", "edge", "license:apache-2.0"],
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
    assert item["metrics"]["commercial_license_status"] == "permissive"
    assert item["metrics"]["commercial_direct_reuse_ready"] is True
    assert "硬件开发" in item["metrics"]["priority_tags"]


def test_noncommercial_hardware_model_is_filtered_before_report(monkeypatch):
    restricted = _model(
        "org/nc-edge-camera",
        "object-detection",
        "tflite",
        ["edge-ai", "embedded", "security-camera", "license:cc-by-nc-4.0"],
        downloads=9000,
        likes=100,
    )

    def fake_get(url, **kwargs):
        if url == huggingface.API:
            return FakeResponse(payload=[restricted])
        if url.endswith("/org/nc-edge-camera/raw/main/README.md"):
            return FakeResponse(
                text=(
                    "# Edge Camera\nOn-device object detection for an embedded smart security camera "
                    "with real-time inference and consumer hardware deployment."
                )
            )
        return FakeResponse(status_code=404)

    monkeypatch.setattr(huggingface.requests, "get", fake_get)
    assert huggingface.HuggingFaceCollector().collect(limit=10) == []


def test_unknown_license_hardware_model_is_not_treated_as_commercial_product_candidate(monkeypatch):
    unknown = _model(
        "org/unknown-edge-camera",
        "object-detection",
        "tflite",
        ["edge-ai", "embedded", "security-camera"],
        downloads=10000,
        likes=200,
    )

    def fake_get(url, **kwargs):
        if url == huggingface.API:
            return FakeResponse(payload=[unknown])
        if url.endswith("/org/unknown-edge-camera/raw/main/README.md"):
            return FakeResponse(
                text=(
                    "# Edge Camera\nOn-device object detection for an embedded smart security camera "
                    "with production deployment and measured latency."
                )
            )
        return FakeResponse(status_code=404)

    monkeypatch.setattr(huggingface.requests, "get", fake_get)
    assert huggingface.HuggingFaceCollector().collect(limit=10) == []


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
