from datetime import datetime, timezone

from app.deployment_readiness import (
    attach_deployment_metrics,
    deployment_readiness,
    github_engineering_readiness,
    huggingface_deployment_readiness,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_github_real_engineering_repo_is_ready():
    item = {
        "source": "github",
        "metrics": {
            "primary_lane": "开发基础设施",
            "repo_size_kb": 180,
            "language": "Python",
            "readme_evidence": True,
            "readme_chars": 1200,
            "pushed_at": _now(),
            "commercial_license_status": "permissive",
        },
    }
    result = github_engineering_readiness(item)
    assert result["eligible"] is True
    assert result["score"] >= 60
    assert any("仓库体量" in value for value in result["evidence"])
    assert any("代码提交" in value for value in result["evidence"])


def test_github_empty_hype_repo_is_rejected_even_if_named_like_product():
    item = {
        "source": "github",
        "title": "Amazing AI Commerce Platform",
        "description": "Next generation AI platform",
        "metrics": {
            "primary_lane": "跨境业务工具",
            "repo_size_kb": 0,
            "language": "",
            "readme_evidence": False,
            "readme_chars": 0,
            "pushed_at": _now(),
            "commercial_license_status": "unknown",
        },
    }
    result = github_engineering_readiness(item)
    assert result["eligible"] is False
    assert "代码体量" in result["reason"] or "README" in result["reason"]


def test_github_readme_only_repo_is_not_treated_as_real_code_product():
    item = {
        "source": "github",
        "title": "AI Seller Platform Concept",
        "description": "Amazon seller platform concept with detailed architecture documentation",
        "metrics": {
            "primary_lane": "跨境业务工具",
            "repo_size_kb": 2,
            "language": "",
            "readme_evidence": True,
            "readme_chars": 4200,
            "pushed_at": _now(),
            "commercial_license_status": "permissive",
        },
    }
    result = github_engineering_readiness(item)
    assert result["eligible"] is False
    assert "代码体量" in result["reason"]


def test_github_archived_repo_is_rejected():
    result = github_engineering_readiness(
        {
            "source": "github",
            "metrics": {
                "archived": True,
                "repo_size_kb": 5000,
                "language": "Python",
                "readme_evidence": True,
                "readme_chars": 2000,
                "pushed_at": _now(),
                "commercial_license_status": "permissive",
            },
        }
    )
    assert result["eligible"] is False
    assert "归档" in result["reason"]


def test_huggingface_hardware_model_requires_real_deployment_signal():
    item = {
        "source": "huggingface",
        "title": "org/security-camera-model",
        "description": "Smart security camera object detection model for consumer hardware",
        "metrics": {
            "primary_lane": "实体商品/硬件",
            "pipeline_tag": "object-detection",
            "library_name": "transformers",
            "model_card_evidence": True,
            "model_card_chars": 1200,
            "commercial_license_status": "permissive",
            "tags": ["computer-vision", "camera"],
        },
    }
    result = huggingface_deployment_readiness(item)
    assert result["eligible"] is False
    assert "部署证据" in result["reason"]


def test_huggingface_hardware_model_with_tflite_int8_is_ready():
    item = {
        "source": "huggingface",
        "title": "org/edge-security-camera",
        "description": "TFLite INT8 quantized object detector for on-device smart security cameras",
        "metrics": {
            "primary_lane": "实体商品/硬件",
            "pipeline_tag": "object-detection",
            "library_name": "tflite",
            "model_card_evidence": True,
            "model_card_chars": 1400,
            "commercial_license_status": "permissive",
            "tags": ["tflite", "int8", "edge-ai", "camera"],
        },
    }
    result = huggingface_deployment_readiness(item)
    assert result["eligible"] is True
    assert result["score"] >= 70
    assert any("部署信号" in value for value in result["evidence"])


def test_huggingface_without_model_card_is_not_ready():
    item = {
        "source": "huggingface",
        "description": "ONNX INT8 edge model",
        "metrics": {
            "primary_lane": "实体商品/硬件",
            "pipeline_tag": "object-detection",
            "library_name": "onnxruntime",
            "model_card_evidence": False,
            "commercial_license_status": "permissive",
            "tags": ["onnx", "int8"],
        },
    }
    result = huggingface_deployment_readiness(item)
    assert result["eligible"] is False
    assert "Model Card" in result["reason"]


def test_non_code_source_does_not_get_blocked_by_deployment_gate():
    result = deployment_readiness({"source": "arxiv"})
    assert result["eligible"] is True


def test_attach_deployment_metrics_preserves_evidence_for_deepseek():
    item = {
        "source": "github",
        "metrics": {"opportunity_evidence": ["原始机会证据"]},
    }
    result = {
        "eligible": True,
        "score": 82,
        "reason": "具备真实工程资产",
        "evidence": ["主要语言:Python", "近14天有代码提交"],
    }
    attach_deployment_metrics(item, result)
    metrics = item["metrics"]
    assert metrics["deployment_ready"] is True
    assert metrics["deployment_readiness_score"] == 82
    assert any(str(value).startswith("部署成熟度:") for value in metrics["opportunity_evidence"])
    assert "原始机会证据" in metrics["opportunity_evidence"]
