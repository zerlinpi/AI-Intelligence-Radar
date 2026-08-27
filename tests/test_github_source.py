from datetime import datetime, timezone

from app.sources import github


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


def _repo(repo_id, name, description, topics, stars=20, license_spdx="MIT", size_kb=240):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": repo_id,
        "name": name,
        "full_name": f"owner/{name}",
        "html_url": f"https://github.com/owner/{name}",
        "description": description,
        "created_at": now,
        "updated_at": now,
        "pushed_at": now,
        "stargazers_count": stars,
        "forks_count": 3,
        "open_issues_count": 1,
        "size": size_kb,
        "topics": topics,
        "language": "Python",
        "license": {"spdx_id": license_spdx},
        "default_branch": "main",
        "homepage": "",
    }


def test_github_readme_enrichment_rejects_demo_and_keeps_hardware(monkeypatch):
    demo = _repo(
        1,
        "generic-ai-runtime",
        "AI runtime framework demo",
        ["ai", "runtime", "agent"],
        stars=200,
    )
    hardware = _repo(
        2,
        "esp32-edge-camera",
        "Embedded computer vision runtime for ESP32 camera hardware",
        ["esp32", "edge-ai", "computer-vision", "camera"],
        stars=30,
    )

    def fake_get(url, **kwargs):
        if url == github.SEARCH_API:
            return FakeResponse(payload={"items": [demo, hardware]})
        if url.endswith("/generic-ai-runtime/readme"):
            return FakeResponse(
                text="# Demo\nTutorial example app and starter template for learning an AI runtime."
            )
        if url.endswith("/esp32-edge-camera/readme"):
            return FakeResponse(
                text=(
                    "# ESP32 Edge Camera\nProduction-oriented embedded edge AI runtime for an ESP32 "
                    "camera with on-device object detection, BLE sensor integration, firmware APIs "
                    "and a reference design for smart pet and home camera prototypes."
                )
            )
        return FakeResponse(status_code=404)

    monkeypatch.setattr(github.requests, "get", fake_get)

    results = github.GithubCollector().collect(limit=10)
    titles = [item["title"] for item in results]

    assert "owner/esp32-edge-camera" in titles
    assert "owner/generic-ai-runtime" not in titles

    item = next(row for row in results if row["title"] == "owner/esp32-edge-camera")
    assert "README:" in item["description"]
    assert "Production-oriented embedded edge AI runtime" in item["description"]
    assert "license: MIT" in item["description"]
    assert item["metrics"]["repo_size_kb"] == 240
    assert item["metrics"]["readme_evidence"] is True
    assert item["metrics"]["readme_chars"] > 100
    assert item["metrics"]["license_spdx"] == "MIT"
    assert item["metrics"]["report_eligible"] is True
    assert item["metrics"]["deployment_ready"] is True
    assert item["metrics"]["deployment_readiness_score"] >= 35


def test_clean_readme_removes_badges_images_and_code_blocks():
    cleaned = github._clean_readme(
        "# Tool\n![badge](https://img.example/badge.svg)\n"
        "Use [the SDK](https://example.com/sdk) for embedded products.\n"
        "```python\nprint('noise')\n```"
    )

    assert "badge.svg" not in cleaned
    assert "print('noise')" not in cleaned
    assert "the SDK" in cleaned
    assert "embedded products" in cleaned
