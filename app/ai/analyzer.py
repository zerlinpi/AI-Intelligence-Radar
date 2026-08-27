import json
import re
from datetime import datetime, timezone
from typing import Dict, List

from app.ai.client import (
    call_llm_with_retry,
    get_llm_client,
    get_llm_model,
)
from app.config import (
    LLM_API_KEY,
    LLM_MAX_TOKENS,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
)
from app.content_quality import distinct_sentences
from app.core.logger import get_logger


logger = get_logger("AI分析")

# DeepSeek V4 Pro 上下文足够大。这里只保留防止异常抓取内容无限膨胀的安全预算，
# 不再用几百字符的限制损失论文摘要、模型标签和项目技术说明。
MAX_PROJECT_DESCRIPTION_CHARS = 6000
MAX_POLICY_DESCRIPTION_CHARS = 12000
MAX_TITLE_CHARS = 500
MAX_BATCH_ITEMS = 14

# DeepSeek V4 Pro 模型能力硬上限；实际请求仍由 LLM_MAX_TOKENS 控制。
MAX_OUTPUT_TOKENS = 384000

SOURCE_NAMES = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
    "amazon_policy": "Amazon",
    "us_import_rule": "美国海关 CBP",
    "cpsc_compliance": "CPSC",
    "fda_compliance": "FDA",
    "fcc_compliance": "FCC",
}

OPPORTUNITY_MAP = {
    "高": "high",
    "中": "medium",
    "低": "low",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

METRIC_LABELS = {
    "stars": "星",
    "forks": "分",
    "upvotes": "票",
    "comments": "评",
    "downloads": "下",
    "likes": "赞",
    "momentum": "势",
    "policy_score": "政",
    "opportunity_score": "机",
    "selection_score": "选",
}


def _local_trend_score(item: Dict) -> float:
    try:
        return round(float(item.get("trend_score", 50) or 50), 2)
    except (TypeError, ValueError):
        return 50


def _is_policy(item: Dict) -> bool:
    return str(item.get("category") or "").lower() == "policy"


def _clean_original_description(item: Dict) -> str:
    """模型异常时保留数据源原始说明，不主动截断业务正文。"""
    description = " ".join(str(item.get("description") or "").split())
    if description:
        return description

    title = " ".join(str(item.get("title") or "").split())
    if title:
        return f"公开数据源暂未提供更详细说明，项目名称为 {title}。"

    return "公开数据源暂未提供足够的项目说明。"


def _fallback_result(item: Dict, reason: str = "") -> Dict:
    if reason:
        logger.warning("AI 分析降级：%s", reason)

    original = _clean_original_description(item)

    if _is_policy(item):
        return {
            "purpose": f"官方原始说明：{original}",
            "summary": (
                "本条政策的 AI 结构化分析未完成；请优先依据官方原文核对适用产品、"
                "生效时间、进口主体及测试/证书要求。"
            ),
            "affected_products": "请依据官方原文核对具体适用产品、功能特征与豁免范围。",
            "risk": "AI 风险拆分未完成；在确认适用范围前，不应假设现有产品已经满足准入要求。",
            "preparation": "先保存官方原文，并核对该产品对应的测试、证书、注册、标签或申报资料。",
            "trend_score": 0,
            "business_score": 50,
            "opportunity": "medium",
            "startup_ideas": ["先核对官方原文，并按产品类别整理对应合规资料"],
            "llm_meta": {
                "success": False,
                "fallback": True,
                "reason": reason,
            },
        }

    metrics = item.get("metrics") or {}
    tags = metrics.get("priority_tags") if isinstance(metrics, dict) else []
    tag_text = "、".join(str(tag) for tag in tags or [] if str(tag).strip())
    if tag_text:
        summary = (
            f"本条 AI 深度分析未完成；本地筛选已将其识别为“{tag_text}”候选，"
            "可先结合原始说明、技术信号和增长数据判断是否继续跟进。"
        )
    else:
        summary = "本条 AI 深度分析未完成；可先结合项目原始说明与增长信号判断是否继续跟进。"

    return {
        "purpose": f"项目原始说明：{original}",
        "summary": summary,
        "affected_products": "",
        "risk": "",
        "preparation": "",
        "trend_score": _local_trend_score(item),
        "business_score": 50,
        "opportunity": "medium",
        "startup_ideas": [],
        "llm_meta": {
            "success": False,
            "fallback": True,
            "reason": reason,
        },
    }


def _compact_metrics(item: Dict) -> str:
    metrics = item.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    parts = []
    for key, label in METRIC_LABELS.items():
        value = metrics.get(key, item.get(key))
        if value not in (None, "", 0, 0.0):
            parts.append(f"{label}={value}")

    tags = metrics.get("priority_tags") or []
    if isinstance(tags, list) and tags:
        parts.append("标=" + "/".join(str(tag) for tag in tags))

    dimensions = metrics.get("opportunity_dimensions") or {}
    if isinstance(dimensions, dict) and dimensions:
        dimension_labels = {
            "cross_border": "跨",
            "technical_frontier": "技",
            "hardware_enablement": "硬",
            "physical_product": "实",
        }
        dimension_text = "/".join(
            f"{dimension_labels.get(key, key)}{value}"
            for key, value in dimensions.items()
            if value not in (None, "", 0, 0.0)
        )
        if dimension_text:
            parts.append("维=" + dimension_text)

    eligibility_reason = str(metrics.get("eligibility_reason") or "").strip()
    if eligibility_reason:
        parts.append("资=" + eligibility_reason)

    primary_lane = str(metrics.get("primary_lane") or "").strip()
    if primary_lane:
        parts.append("道=" + primary_lane)

    primary_use_case = str(metrics.get("primary_use_case") or "").strip()
    if primary_use_case:
        parts.append("场=" + primary_use_case)

    product_categories = metrics.get("product_categories") or []
    if isinstance(product_categories, list) and product_categories:
        parts.append("品=" + "/".join(str(value) for value in product_categories))

    evidence = metrics.get("opportunity_evidence") or []
    if isinstance(evidence, list) and evidence:
        parts.append("据=" + "/".join(str(value) for value in evidence[:5]))

    if _is_policy(item):
        focus = str(metrics.get("policy_focus") or "").strip()
        authority = str(metrics.get("policy_authority") or "").strip()
        kind = str(metrics.get("policy_kind") or "").strip()
        if focus:
            parts.append(f"焦={focus}")
        if authority:
            parts.append(f"机={authority}")
        if kind:
            parts.append(f"类={kind}")

    return ";".join(parts)


def _age_hours(item: Dict):
    created_at = item.get("created_at")
    if not created_at:
        return None

    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(round((datetime.now(timezone.utc) - created).total_seconds() / 3600), 0)
    except Exception:
        return None


def _compact_item(item: Dict, index: int) -> list:
    title = str(item.get("title") or "")[:MAX_TITLE_CHARS]
    description = " ".join(str(item.get("description") or "").split())
    description_limit = (
        MAX_POLICY_DESCRIPTION_CHARS
        if _is_policy(item)
        else MAX_PROJECT_DESCRIPTION_CHARS
    )
    description = description[:description_limit]
    source = str(item.get("source") or "")
    item_type = "政" if _is_policy(item) else "项"

    return [
        index,
        item_type,
        title,
        description,
        SOURCE_NAMES.get(source, source),
        _age_hours(item),
        round(float(item.get("trend_score") or 0), 1),
        _compact_metrics(item),
    ]


def _extract_json_object(content: str) -> Dict:
    if not content:
        return {}

    text = content.strip()
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()

    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            result = json.loads(match.group(0))
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}


def _read_result_row(row):
    """读取紧凑数组格式，同时兼容旧数组和字典格式。"""
    if isinstance(row, list) and len(row) >= 9:
        return {
            "序号": row[0],
            "用途": row[1],
            "摘要": row[2],
            "商业分": row[3],
            "机会": row[4],
            "建议": row[5],
            "影响产品": row[6],
            "风险": row[7],
            "准备资料": row[8],
        }

    if isinstance(row, list) and len(row) >= 6:
        return {
            "序号": row[0],
            "用途": row[1],
            "摘要": row[2],
            "商业分": row[3],
            "机会": row[4],
            "建议": row[5],
            "影响产品": "",
            "风险": "",
            "准备资料": "",
        }

    if isinstance(row, list) and len(row) >= 5:
        return {
            "序号": row[0],
            "用途": "",
            "摘要": row[1],
            "商业分": row[2],
            "机会": row[3],
            "建议": row[4],
            "影响产品": "",
            "风险": "",
            "准备资料": "",
        }

    if isinstance(row, dict):
        return row

    return None


def _result_indexes(raw: Dict) -> set:
    rows = raw.get("结果") if isinstance(raw, dict) else None
    indexes = set()
    if not isinstance(rows, list):
        return indexes

    for raw_row in rows:
        row = _read_result_row(raw_row)
        if not row:
            continue
        try:
            indexes.add(int(row.get("序号")))
        except (TypeError, ValueError):
            continue
    return indexes


def _merge_raw_results(base: Dict, extra: Dict) -> Dict:
    base_rows = base.get("结果") if isinstance(base, dict) else None
    extra_rows = extra.get("结果") if isinstance(extra, dict) else None

    merged = list(base_rows) if isinstance(base_rows, list) else []
    if isinstance(extra_rows, list):
        merged.extend(extra_rows)
    return {"结果": merged}


def _merge_usage(*metas: Dict) -> Dict:
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    for meta in metas:
        current = (meta or {}).get("usage") or {}
        for key in usage:
            try:
                usage[key] += int(current.get(key, 0) or 0)
            except (TypeError, ValueError):
                pass
    return usage


def _dedupe_generated_fields(item: Dict, purpose: str, summary: str, idea: str,
                             affected_products: str, risk: str, preparation: str):
    """模型已经被要求分工写作；这里再删除明显的同义复述句作为保险。"""
    if _is_policy(item):
        cleaned_summary = distinct_sentences(summary, [purpose], threshold=0.80)
        if cleaned_summary:
            summary = cleaned_summary

        cleaned_affected = distinct_sentences(
            affected_products,
            [purpose, summary],
            threshold=0.84,
        )
        affected_products = cleaned_affected

        cleaned_risk = distinct_sentences(
            risk,
            [purpose, summary, affected_products],
            threshold=0.80,
        )
        risk = cleaned_risk

        cleaned_idea = distinct_sentences(
            idea,
            [purpose, summary, affected_products, risk],
            threshold=0.76,
        )
        idea = cleaned_idea

        cleaned_preparation = distinct_sentences(
            preparation,
            [purpose, summary, affected_products, risk, idea],
            threshold=0.76,
        )
        preparation = cleaned_preparation
    else:
        cleaned_summary = distinct_sentences(summary, [purpose], threshold=0.80)
        if cleaned_summary:
            summary = cleaned_summary
        idea = distinct_sentences(idea, [purpose, summary], threshold=0.76)

    return purpose, summary, idea, affected_products, risk, preparation


def _normalize_batch_result(raw: Dict, items: List[Dict], meta: Dict) -> List[Dict]:
    rows = raw.get("结果") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return [_fallback_result(item, "模型返回格式无效") for item in items]

    by_index = {}
    for raw_row in rows:
        row = _read_result_row(raw_row)
        if not row:
            continue
        try:
            index = int(row.get("序号"))
        except (TypeError, ValueError):
            continue
        by_index[index] = row

    results = []
    for index, item in enumerate(items, start=1):
        row = by_index.get(index)
        if not row:
            results.append(_fallback_result(item, f"缺少第 {index} 条分析结果"))
            continue

        try:
            business_score = float(row.get("商业分", 50) or 50)
        except (TypeError, ValueError):
            business_score = 50
        business_score = round(min(max(business_score, 0), 100), 2)

        opportunity = OPPORTUNITY_MAP.get(
            str(row.get("机会") or "中").strip().lower(),
            "medium",
        )
        purpose = str(row.get("用途") or "").strip()
        summary = str(row.get("摘要") or "").strip()
        idea = str(row.get("建议") or "").strip()
        affected_products = str(row.get("影响产品") or "").strip()
        risk = str(row.get("风险") or "").strip()
        preparation = str(row.get("准备资料") or "").strip()

        (
            purpose,
            summary,
            idea,
            affected_products,
            risk,
            preparation,
        ) = _dedupe_generated_fields(
            item,
            purpose,
            summary,
            idea,
            affected_products,
            risk,
            preparation,
        )

        results.append(
            {
                "purpose": purpose or f"项目原始说明：{_clean_original_description(item)}",
                "summary": summary or "暂无新增的独立价值判断。",
                "affected_products": affected_products,
                "risk": risk,
                "preparation": preparation,
                "trend_score": 0 if _is_policy(item) else _local_trend_score(item),
                "business_score": business_score,
                "opportunity": opportunity,
                "startup_ideas": [idea] if idea else [],
                "llm_meta": meta,
            }
        )

    return results


def _build_prompt(compact_json: str) -> str:
    return (
        "你是美国跨境电商合规、早期技术和产品机会分析师。数组每项为"
        "[序号,类型(政/项),名称,简介,来源,时间小时,热度,指标]。"
        "总原则：完整、准确、有决策价值优先；不要为了精简而省略关键条件，也不要为了写长而重复。"
        "所有判断必须基于提供的数据；证据不足时明确写需验证，不得把猜测或营销措辞写成事实。"
        "【去重复写作协议】每个字段必须承担不同职责。禁止把同一句事实换同义词重复到相邻字段；"
        "若某字段没有新增信息，允许返回空字符串，不得为了填满字段而复述。"
        "用途/核心变化只写客观事实和工作机制，不写‘值得关注’、商业评价或建议；"
        "判断/影响只写为什么对我们的跨境经营、开发效率、硬件或实体商品有价值，以及限制、缺口和不确定性，"
        "不得重新介绍已经在用途字段写过的功能；建议只写一个最优先的可执行动作或验证实验，不再介绍项目。"
        "热度高、发布时间近只能作为排序信号，不能单独写成价值判断。"
        "类型=政时，优先分析Amazon政策与审核、美国进口清关新规、美国市场产品合规审核。"
        "Amazon重点看商品合规、Testing/Inspection/Certification、Account Health、Listing前置审核、"
        "受限产品和高风险品类；美国进口重点看CBP、关税、de minimis、电子申报、进口商责任；"
        "产品审核重点看CPSC的CPC/GCC/eFiling与实验室测试、FDA注册/产品列名/进口要求、"
        "FCC RF设备Equipment Authorization。"
        "政策用途必须说明政策到底改了什么、适用什么产品/卖家，并尽量保留生效日期、阈值、"
        "测试标准、证书、注册或申报要求；政策判断只说明对美国销售、上架、进口、清关或账号的具体影响；"
        "政策建议只给最优先的实际动作，不得重复核心变化。"
        "若指标中焦=产品合规审核，必须额外拆分影响产品、风险、准备资料三个字段。"
        "影响产品只写官方信息能够支持的具体产品类别、功能特征、设备类型或适用范围；"
        "风险只写不满足要求可能造成的上架、进口、清关、召回、整改或执法后果；"
        "准备资料只列与该规则直接相关的测试报告、CPC/GCC、eFiling字段、FDA注册/列名、FCC授权、"
        "标签、说明书或其他资料，不要重复风险或建议。若不是产品合规审核，这三个字段返回空字符串。"
        "类型=项时，不得只按热度和发布时间判断。必须同时审视四条机会路径："
        "第一，跨境电商实用性：是否能直接改善Amazon、Shopify、TikTok Shop、独立站的选品、Listing、"
        "广告、SEO、本地化、客服、竞品、定价、物流、库存、评论、达人营销或运营自动化；"
        "第二，技术前沿/工程创新：是否提出新的Agent、Memory、RAG、推理、模型、运行时、编译、"
        "多模态、机器人、视觉/语音或开发框架范式，是否能显著降低成本或提升能力。"
        "只有材料能支持时才能称为首创/突破，不得因为标题出现novel/new就自动判定开创性；"
        "第三，硬件开发价值：是否可用于嵌入式、MCU、BLE/IoT、边缘AI、传感器、摄像头、机器人、"
        "运动控制、语音、视觉或其他真实硬件系统；"
        "第四，美国市场实体商品机会：技术是否能形成或升级消费者可购买的家居、厨房、宠物、运动、"
        "户外、汽车、工具、穿戴、健康辅助、智能设备等实体产品，并说明实现路径及工程/合规不确定性。"
        "指标中的资=本地资格判断理由，维=四维机会分，道=本地机会大类，场=主要使用场景，"
        "品=候选商品品类，据=本地真实证据；这些是辅助证据，不得原样抄成结论，必须结合简介判断。"
        "当标包含硬件开发/实体商品机会，或品=非空时，禁止只写‘可做智能硬件/摄像头/机器人’这类泛结论。"
        "判断字段必须在证据允许范围内明确：可转化的具体商品形态、关键技术模块或算力/传感/连接要求、"
        "主要工程风险，以及美国销售可能需要先确认的合规方向；无法从证据确认的部分必须写‘需验证’。"
        "建议字段必须给一个单一MVP验证计划：说明优先使用的原型平台或关键BOM模块，并给出2到4个最关键的"
        "量化验证指标，例如端到端延迟、RAM/Flash、功耗、温升、识别准确率、误报率、续航、BOM成本或稳定性，"
        "同时写清满足什么条件才进入下一阶段。涉及Bluetooth/Wi-Fi/RF、消费品安全、儿童用品、健康/医疗相关"
        "产品时，应指出先确认FCC/CPSC/FDA等适用性，但不得在材料没有提供时编造具体标准号或认证结论。"
        "GitHub项目重点看代码是否真实可复用、工程门槛和开发效率；据=若包含代码文件、包/构建配置、测试、CI、"
        "部署配置等文件树证据，应优先据此判断工程成熟度，不得把README或Star本身当作真实代码成熟度。"
        "Hugging Face模型重点看模型任务能力、部署条件、端侧/边缘可能性和可嵌入产品的场景；"
        "arXiv重点看能否进入跨境业务、硬件或实体商品，不再为了学术新颖性本身写长篇介绍；"
        "Product Hunt重点看真实需求和现有产品验证。"
        "商业分不是‘电商相关度分’：只要四条路径中至少一条价值强、落地路径清晰，就可以高分；"
        "但仅有热度、普通套壳、没有技术差异或没有真实使用路径的项目不应高分。"
        "项目用途字段必须只回答‘它实际能做什么/怎么工作/给谁用’，不要评价；"
        "项目判断字段必须只回答‘为什么值得进入我们的雷达、相对现有方案新增了什么价值、还缺什么验证’，"
        "至少包含一个价值理由或限制条件，不得复述用途；"
        "项目建议字段必须给一个具体下一步，例如接入现有流程、做MVP、验证模型、测BOM/延迟/准确率/ROI，"
        "尽量写清验证对象和成功条件，不得重复用途或判断。"
        "不要因历史规模或品牌知名度加分。必须返回合法 JSON，且不得遗漏输入中的任何序号。"
        "JSON结构严格为："
        '{"结果":[[序号,"用途","判断",分数,"高|中|低","建议","影响产品","风险","准备资料"]]}。'
        "项目以及非产品合规审核政策的最后三个字段必须返回空字符串。"
        f"数据={compact_json}"
    )


def analyze_items(items: List[Dict]) -> List[Dict]:
    """一次请求同时分析美国经营合规政策与早期产品项目。"""
    items = list(items or [])[:MAX_BATCH_ITEMS]
    if not items:
        return []

    if not LLM_API_KEY:
        return [_fallback_result(item, "缺少 LLM API 密钥") for item in items]

    output_tokens = min(max(int(LLM_MAX_TOKENS or 1), 1), MAX_OUTPUT_TOKENS)
    client = get_llm_client()

    def request_for(compact_rows):
        compact_json = json.dumps(compact_rows, ensure_ascii=False, separators=(",", ":"))
        kwargs = {
            "model": get_llm_model(),
            "messages": [{"role": "user", "content": _build_prompt(compact_json)}],
            "max_tokens": output_tokens,
            "response_format": {"type": "json_object"},
        }

        if str(LLM_PROVIDER or "").lower() == "deepseek":
            kwargs["reasoning_effort"] = "max"
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            kwargs["temperature"] = LLM_TEMPERATURE

        return client.chat.completions.create(**kwargs)

    compact_items = [
        _compact_item(item, index)
        for index, item in enumerate(items, start=1)
    ]

    response, meta = call_llm_with_retry(
        lambda: request_for(compact_items),
        retries=1,
    )

    if not meta.get("success") or response is None:
        reason = meta.get("error", "模型请求失败")
        return [_fallback_result(item, reason) for item in items]

    all_metas = [meta]

    try:
        choice = response.choices[0]
        content = choice.message.content or ""
        finish_reason = getattr(choice, "finish_reason", "") or ""
        parsed = _extract_json_object(content)

        if not parsed:
            logger.warning(
                "模型首次结构化结果无效，尝试恢复一次：结束原因=%s",
                finish_reason,
            )
            retry_response, retry_meta = call_llm_with_retry(
                lambda: request_for(compact_items),
                retries=1,
            )
            all_metas.append(retry_meta)
            if retry_meta.get("success") and retry_response is not None:
                response = retry_response
                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = getattr(choice, "finish_reason", "") or ""
                parsed = _extract_json_object(content)

        present = _result_indexes(parsed)
        missing_indexes = [
            index
            for index in range(1, len(items) + 1)
            if index not in present
        ]
        if parsed and missing_indexes:
            logger.warning(
                "模型批量结果缺少序号=%s，单独恢复缺失条目",
                missing_indexes,
            )
            missing_rows = [
                _compact_item(items[index - 1], index)
                for index in missing_indexes
            ]
            missing_response, missing_meta = call_llm_with_retry(
                lambda: request_for(missing_rows),
                retries=1,
            )
            all_metas.append(missing_meta)
            if missing_meta.get("success") and missing_response is not None:
                missing_content = missing_response.choices[0].message.content or ""
                missing_parsed = _extract_json_object(missing_content)
                if missing_parsed:
                    parsed = _merge_raw_results(parsed, missing_parsed)

        combined_meta = dict(meta)
        combined_meta["usage"] = _merge_usage(*all_metas)
        results = _normalize_batch_result(parsed, items, combined_meta)

        usage = combined_meta.get("usage") or {}
        fallback_count = sum(
            1
            for result in results
            if (result.get("llm_meta") or {}).get("fallback")
        )
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        reasoning_tokens = int(usage.get("reasoning_tokens", 0) or 0)
        visible_tokens = max(completion_tokens - reasoning_tokens, 0)
        logger.info(
            "AI 批量分析完成：条目=%s 降级=%s 输入Token=%s 输出Token=%s "
            "其中推理Token=%s 正文Token=%s 总Token=%s 结束原因=%s",
            len(items),
            fallback_count,
            usage.get("prompt_tokens", 0),
            completion_tokens,
            reasoning_tokens,
            visible_tokens,
            usage.get("total_tokens", 0),
            finish_reason,
        )
        return results
    except Exception as exc:
        return [_fallback_result(item, f"解析模型结果失败：{exc}") for item in items]


def analyze_item(item: Dict) -> Dict:
    """兼容旧调用；单项分析仍复用批量逻辑。"""
    results = analyze_items([item])
    return results[0] if results else _fallback_result(item, "没有可分析条目")