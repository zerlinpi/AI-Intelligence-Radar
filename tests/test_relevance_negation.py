from app.relevance import _strip_negated_application_claims, report_eligibility


def test_negated_application_clause_is_removed_but_positive_contrast_is_kept():
    text = (
        "The benchmark is evaluated without embedded deployment, sensor integration or consumer hardware; "
        "however it also includes an on-device camera implementation with BLE sensors for a wearable device."
    )
    cleaned = _strip_negated_application_claims(text)

    assert "without embedded deployment" not in cleaned
    assert "on-device camera implementation" in cleaned
    assert "BLE sensors" in cleaned


def test_arxiv_negated_hardware_and_commerce_terms_do_not_create_false_eligibility():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Recursive Agent Memory for Long-Horizon Reasoning",
            "description": (
                "This paper studies recursive memory for long-horizon language-model reasoning and "
                "evaluates retrieval quality across synthetic reasoning benchmarks without describing "
                "a cross-border commerce workflow, embedded deployment path, sensor integration or "
                "consumer hardware product application."
            ),
        }
    )

    assert result["technical_frontier"] is True
    assert result["cross_border"] is False
    assert result["hardware_enablement"] is False
    assert result["physical_product"] is False
    assert result["eligible"] is False


def test_positive_hardware_claim_after_contrast_still_qualifies():
    result = report_eligibility(
        {
            "source": "arxiv",
            "title": "Compact Vision Model for Edge Cameras",
            "description": (
                "The baseline analysis does not address ecommerce workflows or cloud seller tooling; "
                "however the proposed method is deployed on-device on an embedded camera, integrates "
                "BLE motion sensors, measures latency and memory use, and targets a battery-powered "
                "smart pet camera consumer device."
            ),
        }
    )

    assert result["eligible"] is True
    assert result["hardware_enablement"] is True
    assert result["physical_product"] is True
