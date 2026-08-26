from app.sources.arxiv import ArxivCollector


class _Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_arxiv_collector_keeps_full_title_and_summary_for_actionable_research(monkeypatch):
    long_title = "On-device Edge AI Vision for Smart Pet Camera Sensors " + "T" * 400
    long_summary = (
        "BEGIN-SUMMARY embedded edge ai object detection for camera sensor smart pet device. "
        + "研究摘要内容。" * 300
        + " END-SUMMARY"
    )
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>{long_title}</title>
        <summary>{long_summary}</summary>
        <published>2026-08-26T00:00:00Z</published>
        <id>https://arxiv.org/abs/2608.99999</id>
        <category term="cs.CV"/>
      </entry>
    </feed>'''

    monkeypatch.setattr(
        "app.sources.arxiv.requests.get",
        lambda *args, **kwargs: _Response(xml),
    )

    rows = ArxivCollector().collect(limit=1)

    assert len(rows) == 1
    assert rows[0]["title"] == long_title
    assert "BEGIN-SUMMARY" in rows[0]["description"]
    assert "END-SUMMARY" in rows[0]["description"]
    assert len(rows[0]["description"]) > 1000
    assert rows[0]["metrics"]["report_eligible"] is True
