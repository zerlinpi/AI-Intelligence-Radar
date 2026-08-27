from app.commercial_readiness import commercial_readiness


def test_github_mit_is_direct_reuse_candidate():
    result = commercial_readiness({
        "source": "github",
        "metrics": {"license_spdx": "MIT"},
    })
    assert result["status"] == "permissive"
    assert result["commercial_candidate"] is True
    assert result["direct_reuse_ready"] is True
    assert result["score"] == 100


def test_github_agpl_is_commercial_but_conditional_not_forbidden():
    result = commercial_readiness({
        "source": "github",
        "metrics": {"license_spdx": "AGPL-3.0"},
    })
    assert result["status"] == "conditional"
    assert result["commercial_candidate"] is True
    assert result["direct_reuse_ready"] is False
    assert result["score"] > 0


def test_github_unknown_license_remains_reference_candidate_only():
    result = commercial_readiness({
        "source": "github",
        "description": "Useful edge AI runtime and compiler for embedded product development.",
        "metrics": {},
    })
    assert result["status"] == "unknown"
    assert result["commercial_candidate"] is True
    assert result["direct_reuse_ready"] is False


def test_unknown_github_with_explicit_noncommercial_readme_is_rejected():
    result = commercial_readiness({
        "source": "github",
        "description": "README: This project is for non-commercial use only.",
        "metrics": {},
    })
    assert result["status"] == "restricted"
    assert result["commercial_candidate"] is False


def test_huggingface_apache_license_tag_is_commercial_candidate():
    result = commercial_readiness({
        "source": "huggingface",
        "metrics": {"tags": ["edge-ai", "license:apache-2.0"]},
    })
    assert result["status"] == "permissive"
    assert result["commercial_candidate"] is True
    assert result["direct_reuse_ready"] is True


def test_huggingface_noncommercial_license_is_rejected():
    result = commercial_readiness({
        "source": "huggingface",
        "metrics": {"tags": ["object-detection", "license:cc-by-nc-4.0"]},
    })
    assert result["status"] == "restricted"
    assert result["commercial_candidate"] is False


def test_huggingface_unknown_license_is_not_a_product_candidate():
    result = commercial_readiness({
        "source": "huggingface",
        "metrics": {"tags": ["edge-ai", "object-detection"]},
    })
    assert result["status"] == "unknown"
    assert result["commercial_candidate"] is False


def test_permissive_license_is_not_overridden_by_generic_research_wording():
    result = commercial_readiness({
        "source": "huggingface",
        "description": "The model was developed for academic research and commercial prototyping.",
        "metrics": {"tags": ["license:apache-2.0"]},
    })
    assert result["status"] == "permissive"
    assert result["commercial_candidate"] is True
