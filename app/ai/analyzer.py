import json
import re
from datetime import datetime, timezone
from typing import Dict, List

from app.ai.client import (
    call_llm_with_retry,
    get_llm_client,
    get_llm_model,
)
from app.config import LLM_API_KEY, LLM_MAX_TOKENS, LLM_TEMPERATURE
from app.core.logger import get_logger


logger = get_logger("AI分析")

# 输入仍做必要去噪，但不再为了省 Token 过度截断有效上下文。
MAX_PROJECT_DESCRIPTION_CHARS = 520
MAX_POLICY_DESCRIPTION_CHARS = 900
MAX_TITLE_CHARS = 140
MAX_BATCH_ITEMS = 14

# 4 条政策 + 10 个项目的一次批量分析需要足够输出空间。
# 8192 是硬上限而不是固定消耗，模型实际只会按需要生成。
MAX_OUTPUT_TOKENS = 8192

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
}


def _local_trend_score(item: Dict) -> float:
    try:
        return round(float(item.get("trend_score", 50) or 50), 2)
    except (TypeError, ValueError):
        return 50


def _is_policy(item: Dict) -> bool:
    return str(item.get("category") or "").lower() == "policy"


def _clean_original_description(item: Dict, limit: int = 360) -> str:
    """在模型异常时尽量保留数据源自己的有效说明，而不是展示空占位。"""
    description = " ".join(str(item.get("description") or "").split())
    if description:
        return description[:limit]

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
            "可先结合原始说明与增长信号判断是否继续跟进。"
        )
    else:
        summary = (
            "本条 AI 深度分析未完成；可先结合项目原始说明与增长信号判断是否继续跟进。"
        )

    return {
        "purpose": f"项目原始说明：{original}",
        "summary": summary,
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
        parts.append("标=" + "/".join(str(tag) for tag in tags[:2]))

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

    # 顺序固定：序号、类型、名称、简介、来源、时间小时、热度、指标。
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
    if isinstance(row, list) and len(row) >= 6:
        return {
            "序号": row[0],
            "用途": row[1],
            "摘要": row[2],
            "商业分": row[3],
            "机会": row[4],
            "建议": row[5],
        }

    if isinstance(row, list) and len(row) >= 5:
        return {
            "序号": row[0],
            "用途": "",
            "摘要": row[1],
            "商业分": row[2],
            "机会": row[3],
            "建议": row[4],
        }

    if isinstance(row, dict):
        return row

    return None


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

        results.append(
            {
                "purpose": purpose or f"项目原始说明：{_clean_original_description(item)}",
                "summary": summary or "暂无 AI 分析摘要。",
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
        "你是美国跨境电商合规与早期AI产品分析师。数组每项为"
        "[序号,类型(政/项),名称,简介,来源,时间小时,热度,指标]。"
        "总原则：完整、准确、有决策价值优先，不要为了精简而省略关键条件、适用对象、"
        "产品类别、日期、阈值、证书、测试要求或实际经营影响；同时避免重复、空话和泛泛而谈。"
        "类型=政时，优先级依次是Amazon政策与审核、美国进口清关新规、美国市场产品合规审核。"
        "Amazon重点看商品合规、Testing/Inspection/Certification、Account Health、"
        "Listing前置审核、受限产品、e-mobility/儿童用品/膳食补充剂等高风险品类。"
        "美国进口重点看CBP、关税、de minimis、电子申报、进口商责任。"
        "产品审核重点看CPSC的CPC/GCC/eFiling与实验室测试、FDA的注册/产品列名/进口要求、"
        "FCC的RF设备Equipment Authorization。"
        "政策用途建议80-140字：说明政策或审核到底改了什么、适用什么产品/卖家，"
        "尽量保留生效日期、阈值、测试标准、证书或注册要求；信息不足时不得编造。"
        "政策判断建议70-120字：说明对美国销售、上架、进口、清关或账号的具体影响，"
        "以及不处理可能造成的后果。"
        "政策建议建议40-80字：列出最应优先准备的测试报告、CPC/GCC、eFiling字段、"
        "FDA注册、FCC授权、标签/说明书或平台审核动作。"
        "类型=项时，重点判断Amazon、Shopify、TikTok Shop、独立站、选品、Listing、广告、"
        "本地化、客服、SEO、竞品、定价、物流、库存、评论、达人营销，以及是否能成为SaaS、"
        "Agent、插件、API或自动化产品。"
        "项目用途建议90-150字：完整说明目标用户、核心功能、输入输出/工作方式、"
        "解决的问题和至少一个典型跨境电商使用场景，让读者不用打开链接也知道项目做什么。"
        "项目判断建议60-100字：综合早期增长信号、用户价值、跨境电商适配度、"
        "竞争壁垒和产品化/付费潜力，说明为什么值得关注或为什么暂不值得追。"
        "项目建议建议35-70字：给出最值得借鉴、组合或开发的具体产品方向，"
        "尽量说明面向哪类卖家或运营环节。"
        "不要因历史规模或品牌知名度加分。必须返回合法 JSON，且不得遗漏输入中的任何序号。"
        "JSON结构严格为："
        '{"结果":[[序号,"用途","判断",分数,"高|中|低","建议"]]}。'
        f"数据={compact_json}"
    )


def analyze_items(items: List[Dict]) -> List[Dict]:
    """一次请求同时分析美国经营合规政策与早期产品项目。"""
    items = list(items or [])[:MAX_BATCH_ITEMS]
    if not items:
        return []

    if not LLM_API_KEY:
        return [_fallback_result(item, "缺少 LLM API 密钥") for item in items]

    compact_items = [
        _compact_item(item, index)
        for index, item in enumerate(items, start=1)
    ]
    compact_json = json.dumps(
        compact_items,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    prompt = _build_prompt(compact_json)

    output_tokens = min(max(int(LLM_MAX_TOKENS or 1), 1), MAX_OUTPUT_TOKENS)

    client = get_llm_client()

    def request():
        return client.chat.completions.create(
            model=get_llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=LLM_TEMPERATURE,
            max_tokens=output_tokens,
            response_format={"type": "json_object"},
        )

    response, meta = call_llm_with_retry(request)

    if not meta.get("success") or response is None:
        reason = meta.get("error", "模型请求失败")
        return [_fallback_result(item, reason) for item in items]

    try:
        choice = response.choices[0]
        content = choice.message.content or ""
        finish_reason = getattr(choice, "finish_reason", "") or ""
        parsed = _extract_json_object(content)

        # DeepSeek JSON Output 偶发可能返回空内容；只在异常时额外恢复一次，
        # 正常日报仍保持一次批量请求。
        if not parsed:
            logger.warning(
                "模型首次结构化结果无效，尝试恢复一次：结束原因=%s",
                finish_reason,
            )
            retry_response, retry_meta = call_llm_with_retry(request, retries=1)
            if retry_meta.get("success") and retry_response is not None:
                response = retry_response
                meta = retry_meta
                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = getattr(choice, "finish_reason", "") or ""
                parsed = _extract_json_object(content)

        results = _normalize_batch_result(parsed, items, meta)

        usage = meta.get("usage") or {}
        fallback_count = sum(
            1
            for result in results
            if (result.get("llm_meta") or {}).get("fallback")
        )
        logger.info(
            "AI 批量分析完成：条目=%s 降级=%s 输入Token=%s 输出Token=%s 总Token=%s 结束原因=%s",
            len(items),
            fallback_count,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
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
