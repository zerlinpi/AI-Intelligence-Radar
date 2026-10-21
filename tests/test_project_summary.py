from app.project_summary import infer_project_summary
from app.report_copy import project_display_description
from app.models.radar_item import RadarItem
from scripts.prepare_local_fallback import _project_analysis


def test_nvr_readme_is_explained_in_chinese_without_leaking_raw_documentation():
    source = (
        "Self-hosted NVR with on-device AI."
        " | topics: rtsp onnx nvr computer-vision"
        " | language: C# | README: Quickstart "
        + "Detailed setup instructions and technical components. " * 80
    )
    summary = infer_project_summary(
        "Flickersoft/serval",
        source,
        tags=["技术前沿", "硬件开发", "实体商品机会"],
        source_name="GitHub",
        metrics={"language": "C#", "repo_code_file_count": 40},
    )
    assert "视频监控/录像" in summary
    assert "端侧/本地推理" in summary
    assert "RTSP" in summary
    assert "README:" not in summary
    assert "Quickstart" not in summary


def test_agent_workflow_and_observability_explain_function_and_user():
    summary = project_display_description(
        "A self-hosted agent workflow and observability toolkit.",
        title="example/agent-tool",
        source_name="GitHub",
        tags=["技术前沿"],
    )
    assert "AI Agent/工作流自动化工具" in summary
    assert "可重复执行的流程" in summary
    assert "运行监控/可观测性工具" in summary


def test_huggingface_task_tag_produces_task_specific_summary():
    summary = project_display_description(
        "task: text-generation | library: transformers | MODEL_CARD: Introduction " +
        "A model readme with full code and CLI tutorials. " * 20,
        title="org/text-model",
        source_name="Hugging Face",
        metrics={"pipeline_tag": "text-generation", "library_name": "transformers"},
    )
    assert "文本生成/大语言模型相关项目" in summary
    assert "MODEL_CARD:" not in summary
    assert "A model readme" not in summary


def test_deterministic_fallback_uses_readme_evidence_not_only_radar_tags():
    item = RadarItem(
        title="Flickersoft/serval",
        source="github",
        url="https://github.com/Flickersoft/serval",
        description=(
            "Self-hosted NVR with on-device AI."
            " | topics: rtsp onnx nvr computer-vision"
            " | language: C# | README: Quickstart "
            + "Detailed setup instructions and technical components. " * 20
        ),
        metrics={
            "priority_tags": ["技术前沿", "硬件开发"],
            "primary_use_case": "实体商品·安防",
            "selection_score": 63,
            "language": "C#",
        },
    )
    result = _project_analysis(item)
    assert "视频监控/录像" in result["purpose"]
    assert "端侧/本地推理" in result["purpose"]
    assert "中文功能摘要尚未完成核验" not in result["purpose"]
    assert result["llm_meta"]["fallback"] is True


def test_unknown_project_does_not_invent_capabilities():
    summary = infer_project_summary(
        "mystery/project",
        "A new project with some source code.",
        tags=["技术前沿", "硬件开发"],
        source_name="GitHub",
        metrics={"language": "Rust", "primary_use_case": "实体商品·安防"},
    )
    assert "不足以确认" in summary
    assert "不能替代" in summary
    assert "机器人" not in summary
