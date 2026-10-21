"""Evidence-based Chinese project summaries for offline/report fallbacks.

This is deliberately deterministic: it never claims a repository feature solely
from popularity or broad radar tags. Specific summaries are produced only when
the public description/README/model-card text contains matching capability cues.
"""
import re
from typing import Iterable


_SPACE = re.compile(r"\s+")
_MARKUP = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[[^\]]+\]\([^)]*\)|<[^>]+>|\x60{3}.*?\x60{3}", re.I | re.S)
_METADATA = re.compile(
    r"\b(?:README|MODEL_CARD|topics|language|license|pipeline_tag|library|tags)\s*:",
    re.I,
)
_CHINESE = re.compile(r"[\u4e00-\u9fff]")


# Most-specific capabilities first. A rule explains what the software/model does,
# not whether it is valuable or mature.
_RULES = [
    (r"\b(?:nvr|network video recorder|video surveillance|surveillance camera system)\b",
     "这是一个面向自托管视频监控/录像的项目，用于管理摄像头视频流或本地录像。"),
    (r"\b(?:mcp server|model context protocol|mcp tools?)\b",
     "这是一个 MCP 工具/服务端，把特定工具或数据接口暴露给兼容的 AI 助手或 Agent 调用；它本身不等于一个独立大模型。"),
    (r"\b(?:browser automation|browser agent|web automation|playwright automation)\b",
     "这是一个网页/浏览器自动化项目，可把浏览器操作、表单处理或重复网页流程交给脚本或 Agent 执行。"),
    (r"\b(?:coding agent|code agent|code review agent|pull request agent|automated code review)\b",
     "这是一个面向软件开发的代码 Agent/审查工具，用于读取代码、辅助修改、检查变更或处理 Pull Request；具体可写入范围需核验。"),
    (r"\b(?:amazon seller|shopify|e-commerce|ecommerce|product listing|listing optimization|marketplace seller)\b",
     "这是一个面向电商卖家/运营团队的工具，围绕商品信息、Listing 或店铺运营流程提供自动化能力；具体支持的渠道和功能以实际页面/代码为准。"),
    (r"\b(?:agent workflow|agent orchestration|multi-agent|agent automation|workflow automation|repeatable workflows)\b",
     "这是一个 AI Agent/工作流自动化工具，用于把任务步骤和工具调用编排成可重复执行的流程，减少人工串联操作。"),
    (r"\b(?:retrieval augmented generation|\brag\b|vector database|vector search|semantic search)\b",
     "这是一个检索/知识库项目，将文档或向量检索接入搜索或大语言模型回答流程，帮助按相关资料返回结果；数据切分与检索质量仍需实测。"),
    (r"\b(?:llm inference server|model serving|inference server|llama\.cpp|vllm|ollama)\b",
     "这是一个模型运行/推理服务项目，用于在本地或服务器加载模型并向应用提供生成或推理接口；实际吞吐和硬件要求需按配置验证。"),
    (r"\b(?:benchmark|evaluation harness|evals|model evaluation|agent evaluation|test suite for agents)\b",
     "这是一个模型/Agent 评测工具，通过可重复的任务或测试衡量输出质量、成功率或回归情况；分数只对其测试集和指标成立。"),
    (r"\b(?:observability|tracing|distributed tracing|logs and metrics|agent monitoring)\b",
     "这是一个运行监控/可观测性工具，收集日志、指标或调用轨迹，帮助开发者定位 Agent、模型或服务的执行问题。"),
    (r"\b(?:object detection|computer vision|image segmentation|visual recognition|vision model)\b",
     "这是一个计算机视觉项目，用于分析图像/视频并执行目标检测、分割或视觉识别；识别类别和精度需以模型及测试结果为准。"),
    (r"\b(?:ocr|optical character recognition|document text extraction)\b",
     "这是一个 OCR/文字提取工具，用于从图片、扫描件或文档图像中识别文字，再供后续搜索或结构化处理。"),
    (r"\b(?:text[- ]to[- ]image|image generation|image generator|stable diffusion|diffusion model)\b",
     "这是一个图像生成/扩散模型项目，依据文本提示或其他条件生成图像；可用分辨率、速度和许可需单独核验。"),
    (r"\b(?:text[- ]to[- ]video|video generation|video generator|video synthesis)\b",
     "这是一个视频生成/合成项目，尝试根据文本、图像或其他条件生成视频内容；输出质量、时长和算力成本需实测。"),
    (r"\b(?:speech recognition|speech[- ]to[- ]text|automatic speech recognition|\bstt\b|whisper)\b",
     "这是一个语音识别/转写项目，将音频转换为文本；支持语言、实时延迟和嘈杂环境准确率需通过样本验证。"),
    (r"\b(?:text[- ]to[- ]speech|speech synthesis|\btts\b|voice cloning)\b",
     "这是一个语音合成项目，将文本转换为语音，部分方案可能涉及音色克隆；需核验授权、语言覆盖和延迟。"),
    (r"\b(?:robotics|robot control|ros ?2|robot operating system|motion planning)\b",
     "这是一个机器人软件/控制项目，涉及机器人感知、任务规划、运动或设备接口；具体可控制的硬件与安全边界需看示例和代码。"),
    (r"\b(?:esp32|embedded firmware|microcontroller|platformio|embedded systems)\b",
     "这是一个嵌入式/固件项目，面向微控制器或边缘设备运行代码并连接外围硬件；实际板卡、内存、功耗和接口兼容性需核验。"),
    (r"\b(?:mqtt|internet of things|\biot\b|sensor telemetry|ble device)\b",
     "这是一个 IoT/设备通信项目，涉及设备、传感器或遥测数据的连接与交换；具体协议、硬件和部署方式需按配置验证。"),
    (r"\b(?:home assistant|smart home|home automation|esphome)\b",
     "这是一个智能家居/设备自动化项目，用于连接设备、读取状态或按规则触发操作；兼容设备范围以集成列表为准。"),
    (r"\b(?:text generation|text-generation|language model|large language model|\bllm\b|chat model)\b",
     "这是一个文本生成/大语言模型相关项目，可根据输入提示生成或处理文本；具体任务能力、上下文限制、部署资源和商用许可需核验。"),
    (r"\b(?:translation|machine translation|localization|i18n|internationalization)\b",
     "这是一个翻译/本地化项目，用于转换文本或适配多语言内容；术语准确性和目标语言覆盖需用真实业务样本检查。"),
    (r"\b(?:document parsing|invoice extraction|structured extraction|pdf parser)\b",
     "这是一个文档解析/信息抽取工具，用于从 PDF 或业务文档中提取文本、字段或结构化数据；字段准确率需用真实文件验证。"),
    (r"\b(?:dashboard|data visualization|analytics dashboard|metrics dashboard)\b",
     "这是一个数据分析/可视化看板项目，把指标或业务数据汇总展示，便于查看趋势和状态；数据源及刷新方式需核验。"),
    (r"\b(?:vulnerability scanner|security scanner|static analysis|secret scanning|dependency scanning)\b",
     "这是一个代码/依赖安全检查工具，用于发现潜在漏洞、泄密或不安全配置；检测覆盖率和误报率需用测试仓库验证。"),
    (r"\b(?:api client|developer sdk|software development kit)\b",
     "这是一个面向开发者的 API/SDK 封装，帮助其他程序调用指定服务；具体端点、认证方式和覆盖范围需查看接口文档。"),
]


def _clean_text(value: str) -> str:
    text = str(value or "")
    text = _MARKUP.sub(" ", text)
    text = _METADATA.sub(" ", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", " ", text)
    text = re.sub(r"[*_~]+", " ", text)
    return _SPACE.sub(" ", text).strip(" |:-")


def _metrics_text(metrics: dict | None) -> str:
    metrics = metrics if isinstance(metrics, dict) else {}
    values = []
    for key in (
        "pipeline_tag", "library_name", "language", "primary_lane",
        "primary_use_case", "product_categories", "topics", "tags",
        "opportunity_evidence",
    ):
        value = metrics.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(str(x) for x in value if x not in (None, ""))
        elif value not in (None, ""):
            values.append(str(value))
    return " ".join(values)


def infer_project_summary(
    title: str,
    description: str,
    *,
    tags: Iterable[str] = (),
    source_name: str = "",
    metrics: dict | None = None,
) -> str:
    """Infer a concise Chinese function summary from source text and structured evidence."""
    clean_description = _clean_text(description)
    tag_values = [str(tag).strip() for tag in (tags or ()) if str(tag).strip()]
    metric_text = _metrics_text(metrics)
    haystack = " ".join(
        str(part or "")
        for part in (title, clean_description, " ".join(tag_values), metric_text)
    ).lower()

    matched = []
    for pattern, summary in _RULES:
        if re.search(pattern, haystack, re.I) and summary not in matched:
            matched.append(summary)
        if len(matched) >= 2:
            break

    if matched:
        summary = " ".join(matched)
        details = []
        if re.search(r"\b(?:on-device ai|edge ai|edge inference|local inference|on-device)\b", haystack):
            details.append("简介还提到端侧/本地推理，实际设备算力、内存和功耗需验证。")
        if re.search(r"\brtsp\b", haystack):
            details.append("文本含 RTSP 视频流线索，需确认实际支持的摄像头协议。")
        if re.search(r"\bonnx\b", haystack):
            details.append("文本提到 ONNX，具体模型格式和运行时支持需以配置为准。")
        if re.search(r"\b(?:esp32|ble|mqtt|ros ?2)\b", haystack):
            details.append("描述包含设备/通信接口线索，需在目标硬件上验证兼容性。")
        if details and len(summary) < 190:
            summary += " " + " ".join(details[:2])
        return summary

    metrics = metrics if isinstance(metrics, dict) else {}
    context = []
    use_case = str(metrics.get("primary_use_case") or "").strip()
    if use_case:
        context.append(f"本地筛选标记的场景为“{use_case}”")
    categories = metrics.get("product_categories") or []
    if isinstance(categories, list) and categories:
        context.append("候选品类为" + "、".join(str(x) for x in categories[:3]))
    tech = []
    for term in ("Python", "TypeScript", "JavaScript", "Rust", "C++", "C#", "ONNX", "PyTorch", "Transformers", "ESP32", "MQTT", "ROS 2", "MCP"):
        if re.search(re.escape(term), haystack, re.I):
            tech.append(term)
    if context or tech:
        evidence = "；".join(context + (["技术线索：" + "、".join(tech[:5])] if tech else []))
        return (
            f"目前公开简介/README不足以确认该项目的具体输入、输出和核心功能。"
            f"可确认的辅助线索：{evidence}。这些线索只能用于定位方向，不能替代对示例和核心代码的核验。"
        )

    return (
        "目前公开简介/README不足以确认该项目具体解决什么问题；"
        "现有文本未提供足够明确的功能、输入输出或使用示例，因此不应仅凭名称或热度猜测。"
        "需要补充项目首页简介、Quickstart 示例或核心入口代码后再下结论。"
    )
