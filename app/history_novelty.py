from datetime import datetime, timedelta, timezone
import re
from typing import Iterable, Tuple

from sqlalchemy.orm import Session

from app.content_quality import copy_similarity
from app.core.logger import get_logger
from app.database.models import IntelligenceItem
from app.models.radar_item import RadarItem
from app.relevance import attach_eligibility_metrics, report_eligibility
from app.storage.repository import exists


logger = get_logger("历史新颖性")

PROJECT_HISTORY_DAYS = 30
POLICY_HISTORY_DAYS = 120
MAX_HISTORY_RECORDS = 800
MAX_HISTORY_SCAN_RECORDS = 2400

# 跨天“同类机会疲劳”只抑制最近已经进入最终日报价值池的高置信重复能力。
# 它与“同一个项目”去重不同：项目名称和 URL 可以不同，但必须 lane/use case 都一致，
# 并且原始能力说明高度相似。窗口故意短于项目历史窗口，避免长期封死一个重要赛道。
OPPORTUNITY_FATIGUE_DAYS = 7
OPPORTUNITY_FATIGUE_SIMILARITY = 0.76
OPPORTUNITY_FATIGUE_MIN_DESCRIPTION_CHARS = 72

# 重复抑制不能把真正的重要变化永久封掉。阈值故意偏保守：
# 只有明显的增长爆发、仓库功能说明实质变化，或官方政策新版本才重新进入雷达。
GITHUB_STAR_GROWTH_RATIO = 2.5
GITHUB_STAR_GROWTH_DELTA = 150
GITHUB_FORK_GROWTH_RATIO = 2.5
GITHUB_FORK_GROWTH_DELTA = 30
PROJECT_TEXT_UPDATE_SIMILARITY = 0.70
PROJECT_UPDATE_MIN_HOURS = 12
POLICY_TEXT_UPDATE_SIMILARITY = 0.82
POLICY_UPDATE_MIN_HOURS = 6

_POLICY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "with", "new", "news", "update", "updates",
    "policy", "policies", "rule", "rules", "requirement", "requirements", "compliance",
    "amazon", "seller", "sellers", "selling", "product", "products", "official",
}

_CRITICAL_FACT_RE = re.compile(
    r"(?:\b20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2})?日?\b|"
    r"\b\d+(?:\.\d+)?\s*%|"
    r"\$\s*\d+(?:[,.]\d+)*(?:\.\d+)?|"
    r"\b\d+(?:[,.]\d+)*(?:\.\d+)?\s*(?:usd|dollars?|days?|hours?|lbs?|kg|mhz|ghz)\b)",
    re.IGNORECASE,
)

# 同一政策主题跨天重新进入雷达时，不能仅因为文章换了一种说法。
# 没有日期/阈值等关键事实变化时，至少要有这种明确的规则变更措辞。
_POLICY_STRONG_CHANGE_RE = re.compile(
    r"\b(?:amended|revised|supersedes?|replaces?|now\s+requires?|will\s+now\s+require|"
    r"no\s+longer|has\s+changed|changes\s+to|effective\s+immediately|takes?\s+effect)\b",
    re.IGNORECASE,
)


def _item_dict(item):
    if isinstance(item, RadarItem):
        return item.to_dict()
    return item if isinstance(item, dict) else {}


def _canonical_title(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^show\s+hn\s*:\s*", "", text)
    if "/" in text and " " not in text:
        text = text.rsplit("/", 1)[-1]
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _policy_tokens(value: str) -> set:
    return {
        token
        for token in _canonical_title(value).split()
        if len(token) >= 3 and token not in _POLICY_STOPWORDS
    }


def _as_utc_naive(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _metric_datetime(data: dict, key: str):
    metrics = data.get("metrics") or {}
    if not isinstance(metrics, dict):
        return None
    return _as_utc_naive(metrics.get(key))


def _record_processed_at(record: IntelligenceItem):
    """优先使用 Radar 处理时间；旧记录没有该字段时回退来源发布时间。"""
    metrics = record.metrics if isinstance(record.metrics, dict) else {}
    processed = _as_utc_naive(metrics.get("history_processed_at"))
    return processed or _as_utc_naive(record.created_at)


def _number(value) -> float:
    try:
        return max(float(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _critical_facts(value: str) -> set:
    return {
        re.sub(r"\s+", "", match.group(0).lower())
        for match in _CRITICAL_FACT_RE.finditer(str(value or ""))
    }


def _record_dict(record: IntelligenceItem) -> dict:
    return {
        "title": record.title or "",
        "url": record.url or "",
        "description": record.description or "",
        "category": record.category or "ai",
        "source": record.source or "unknown",
        "metrics": record.metrics if isinstance(record.metrics, dict) else {},
        # created_at 始终保留来源发布时间，供政策“新版本”比较使用。
        "created_at": record.created_at,
    }


def _same_policy_topic(current: dict, previous: dict) -> bool:
    current_metrics = current.get("metrics") or {}
    previous_metrics = previous.get("metrics") or {}
    current_focus = str(current_metrics.get("policy_focus") or "").strip()
    previous_focus = str(previous_metrics.get("policy_focus") or "").strip()
    if current_focus and previous_focus and current_focus != previous_focus:
        return False

    # 不同监管机构即使标题相似，也不能被当成同一条政策。
    current_authority = str(current_metrics.get("policy_authority") or "").strip().lower()
    previous_authority = str(previous_metrics.get("policy_authority") or "").strip().lower()
    if current_authority and previous_authority and current_authority != previous_authority:
        return False

    left = _canonical_title(current.get("title"))
    right = _canonical_title(previous.get("title"))
    if not left or not right:
        return False
    if left == right:
        return True

    left_tokens = _policy_tokens(left)
    right_tokens = _policy_tokens(right)
    overlap = len(left_tokens & right_tokens)
    containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
    jaccard = overlap / max(len(left_tokens | right_tokens), 1)
    title_similarity = copy_similarity(left, right)

    if containment >= 0.75 or (overlap >= 3 and jaccard >= 0.48):
        return True
    if title_similarity >= 0.82:
        return True

    return (
        title_similarity >= 0.68
        and copy_similarity(
            str(current.get("description") or ""),
            str(previous.get("description") or ""),
        ) >= 0.58
    )


def _same_project(current: dict, previous: dict) -> bool:
    current_url = str(current.get("url") or "").strip()
    previous_url = str(previous.get("url") or "").strip()
    if current_url and previous_url and current_url == previous_url:
        return True

    left = _canonical_title(current.get("title"))
    right = _canonical_title(previous.get("title"))
    if not left or not right:
        return False

    description_similarity = copy_similarity(
        str(current.get("description") or ""),
        str(previous.get("description") or ""),
    )

    if left == right:
        return description_similarity >= 0.30

    title_similarity = copy_similarity(left, right)
    if title_similarity < 0.88:
        return False
    return description_similarity >= 0.44


def _same_historical_item(current: dict, previous: dict) -> bool:
    current_category = str(current.get("category") or "ai").lower()
    previous_category = str(previous.get("category") or "ai").lower()
    if current_category != previous_category:
        return False
    if current_category == "policy":
        return _same_policy_topic(current, previous)
    return _same_project(current, previous)


def _growth_reason(current: dict, previous: dict) -> str:
    # 跨来源的票数/Star口径不同，不用它们判断“重大增长”。
    if str(current.get("source") or "").lower() != "github":
        return ""
    if str(previous.get("source") or "").lower() != "github":
        return ""

    current_metrics = current.get("metrics") or {}
    previous_metrics = previous.get("metrics") or {}
    if not isinstance(current_metrics, dict) or not isinstance(previous_metrics, dict):
        return ""

    current_stars = _number(current_metrics.get("stars", current.get("stars")))
    previous_stars = _number(previous_metrics.get("stars"))
    star_delta = current_stars - previous_stars
    if (
        previous_stars >= 10
        and star_delta >= GITHUB_STAR_GROWTH_DELTA
        and current_stars >= previous_stars * GITHUB_STAR_GROWTH_RATIO
    ):
        return f"GitHub Star 显著增长：{int(previous_stars)}→{int(current_stars)}"

    current_forks = _number(current_metrics.get("forks", current.get("forks")))
    previous_forks = _number(previous_metrics.get("forks"))
    fork_delta = current_forks - previous_forks
    if (
        previous_forks >= 5
        and fork_delta >= GITHUB_FORK_GROWTH_DELTA
        and current_forks >= previous_forks * GITHUB_FORK_GROWTH_RATIO
    ):
        return f"GitHub Fork 显著增长：{int(previous_forks)}→{int(current_forks)}"

    return ""


def _project_material_update_reason(current: dict, previous: dict) -> str:
    growth = _growth_reason(current, previous)
    if growth:
        return growth

    current_url = str(current.get("url") or "").strip()
    previous_url = str(previous.get("url") or "").strip()
    if not current_url or current_url != previous_url:
        return ""
    if str(current.get("source") or "").lower() != "github":
        return ""

    current_push = _metric_datetime(current, "pushed_at") or _metric_datetime(current, "updated_at")
    previous_push = _metric_datetime(previous, "pushed_at") or _metric_datetime(previous, "updated_at")
    if current_push is None or previous_push is None:
        return ""
    if current_push - previous_push < timedelta(hours=PROJECT_UPDATE_MIN_HOURS):
        return ""

    current_description = str(current.get("description") or "")
    previous_description = str(previous.get("description") or "")
    if len(current_description) < 30 or len(previous_description) < 30:
        return ""

    if copy_similarity(current_description, previous_description) < PROJECT_TEXT_UPDATE_SIMILARITY:
        return "GitHub 仓库说明发生实质变化且近期有新代码提交"
    return ""


def _policy_material_update_reason(current: dict, previous: dict) -> str:
    current_time = _as_utc_naive(current.get("created_at"))
    previous_time = _as_utc_naive(previous.get("created_at"))
    if current_time is None or previous_time is None:
        return ""
    if current_time - previous_time < timedelta(hours=POLICY_UPDATE_MIN_HOURS):
        return ""

    current_description = str(current.get("description") or "")
    previous_description = str(previous.get("description") or "")
    if len(current_description) < 45 or len(previous_description) < 45:
        return ""

    similarity = copy_similarity(current_description, previous_description)
    current_facts = _critical_facts(current_description)
    previous_facts = _critical_facts(previous_description)

    # 日期、阈值、金额、时限等关键事实真的变了，才是最强的“新版本”证据。
    if current_facts != previous_facts and (current_facts or previous_facts) and similarity < 0.96:
        return "同一政策主题的新版本包含不同日期、阈值或数值要求"

    # 没有可结构化数值变化时，必须同时存在明确规则变更措辞和显著语义变化。
    # 单纯转载、标题改写或说明顺序变化不再触发重复推送。
    if _POLICY_STRONG_CHANGE_RE.search(current_description) and similarity < 0.72:
        return "同一政策主题出现明确修订、替代或新增要求"

    return ""


def _material_update_reason(current: dict, previous: dict) -> str:
    category = str(current.get("category") or "ai").lower()
    if category == "policy":
        return _policy_material_update_reason(current, previous)
    return _project_material_update_reason(current, previous)


def _mark_material_update(item, reason: str) -> None:
    if not reason:
        return
    if isinstance(item, RadarItem):
        item.metrics = dict(item.metrics or {})
        item.metrics["history_material_update"] = True
        item.metrics["history_material_update_reason"] = reason
        return
    if isinstance(item, dict):
        metrics = item.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
            item["metrics"] = metrics
        metrics["history_material_update"] = True
        metrics["history_material_update_reason"] = reason


def _ensure_project_opportunity_identity(item) -> dict:
    """在历史 Gate 内补齐本地机会身份，不调用任何外部服务。"""
    data = _item_dict(item)
    if str(data.get("category") or "ai").lower() == "policy":
        return data

    metrics = data.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    needs_identity = (
        "report_eligible" not in metrics
        or not str(metrics.get("primary_lane") or "").strip()
        or not str(metrics.get("primary_use_case") or "").strip()
    )
    if not needs_identity:
        return data

    eligibility = report_eligibility(data)
    attach_eligibility_metrics(data, eligibility)
    if isinstance(item, RadarItem):
        item.metrics = dict(data.get("metrics") or {})
    return data


def _historical_opportunity_was_reported(previous: dict) -> bool:
    metrics = previous.get("metrics") or {}
    if not isinstance(metrics, dict):
        return False

    # 新记录可写 final_displayed；部署前的旧记录没有该字段时，回退最终价值 Gate。
    if "final_displayed" in metrics:
        return metrics.get("final_displayed") is True
    return metrics.get("final_report_eligible") is True


def _within_opportunity_fatigue_window(previous: dict) -> bool:
    metrics = previous.get("metrics") or {}
    processed = None
    if isinstance(metrics, dict):
        processed = _as_utc_naive(metrics.get("history_processed_at"))
    processed = processed or _as_utc_naive(previous.get("created_at"))
    if processed is None:
        return False
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=OPPORTUNITY_FATIGUE_DAYS)
    return processed >= cutoff


def _same_recent_opportunity(current: dict, previous: dict) -> bool:
    """不同项目只有在近期已报告、场景一致且能力说明高度相似时才算机会疲劳。"""
    if not _historical_opportunity_was_reported(previous):
        return False
    if not _within_opportunity_fatigue_window(previous):
        return False

    current_metrics = current.get("metrics") or {}
    previous_metrics = previous.get("metrics") or {}
    if not isinstance(current_metrics, dict) or not isinstance(previous_metrics, dict):
        return False
    if current_metrics.get("report_eligible") is not True:
        return False

    current_lane = str(current_metrics.get("primary_lane") or "").strip()
    previous_lane = str(previous_metrics.get("primary_lane") or "").strip()
    current_use_case = str(current_metrics.get("primary_use_case") or "").strip()
    previous_use_case = str(previous_metrics.get("primary_use_case") or "").strip()

    if (
        not current_lane
        or current_lane == "其他"
        or current_lane != previous_lane
        or not current_use_case
        or current_use_case == "其他"
        or current_use_case != previous_use_case
    ):
        return False

    current_description = " ".join(str(current.get("description") or "").split()).strip()
    previous_description = " ".join(str(previous.get("description") or "").split()).strip()
    if min(len(current_description), len(previous_description)) < OPPORTUNITY_FATIGUE_MIN_DESCRIPTION_CHARS:
        return False

    return (
        copy_similarity(current_description, previous_description)
        >= OPPORTUNITY_FATIGUE_SIMILARITY
    )


def _mark_opportunity_fatigue(item, previous: dict) -> None:
    previous_title = str(previous.get("title") or "").strip()
    previous_metrics = previous.get("metrics") or {}
    use_case = str(previous_metrics.get("primary_use_case") or "").strip()
    reason = f"近{OPPORTUNITY_FATIGUE_DAYS}天已报告高度相似的{use_case}机会"
    if previous_title:
        reason += f"：{previous_title}"

    if isinstance(item, RadarItem):
        item.metrics = dict(item.metrics or {})
        item.metrics["history_opportunity_fatigue"] = True
        item.metrics["history_opportunity_fatigue_reason"] = reason
    elif isinstance(item, dict):
        metrics = item.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
            item["metrics"] = metrics
        metrics["history_opportunity_fatigue"] = True
        metrics["history_opportunity_fatigue_reason"] = reason


def _recent_records(db: Session, category: str, days: int) -> list:
    """按 Radar 实际处理时间取历史，而不是按来源发布时间取历史。

    旧数据库记录没有 history_processed_at 时回退 created_at，保持向后兼容。
    查询扫描量有上限，避免长期运行后每次把整张历史表拉进内存。
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(int(days), 1))
    candidates = (
        db.query(IntelligenceItem)
        .filter(IntelligenceItem.category == category)
        .order_by(IntelligenceItem.id.desc())
        .limit(MAX_HISTORY_SCAN_RECORDS)
        .all()
    )
    recent = [
        record
        for record in candidates
        if (_record_processed_at(record) or datetime.min) >= cutoff
    ]
    recent.sort(
        key=lambda record: _record_processed_at(record) or datetime.min,
        reverse=True,
    )
    return recent[:MAX_HISTORY_RECORDS]


def filter_recently_reported(
    db: Session,
    items: Iterable,
    *,
    lookback_days: int | None = None,
) -> Tuple[list, int]:
    """过滤近期已处理内容，但允许有证据的重大更新重新进入雷达。

    第一层处理同 URL / 同项目 / 同政策主题；第二层对项目增加短周期“机会疲劳”控制：
    最近已经进入最终日报价值池、lane/use case 相同且原始能力高度相似的不同项目，
    本轮也不再消耗 DeepSeek Token。重大更新仍按原有规则优先放行。
    """
    rows = list(items or [])
    if not rows:
        return [], 0

    # 项目在进入历史比较前补齐本地机会身份。这里只复用既有本地评分逻辑，不发起网络请求。
    for item in rows:
        _ensure_project_opportunity_identity(item)

    categories = {
        str(_item_dict(item).get("category") or "ai").lower()
        for item in rows
    }
    histories = {}
    for category in categories:
        days = lookback_days
        if days is None:
            days = POLICY_HISTORY_DAYS if category == "policy" else PROJECT_HISTORY_DAYS
        histories[category] = [
            _record_dict(record)
            for record in _recent_records(db, category, days)
        ]

    fresh = []
    duplicates = 0
    fatigue_duplicates = 0
    for item in rows:
        data = _item_dict(item)
        category = str(data.get("category") or "ai").lower()
        previous_match = next(
            (
                previous
                for previous in histories.get(category, [])
                if _same_historical_item(data, previous)
            ),
            None,
        )

        if previous_match is not None:
            update_reason = _material_update_reason(data, previous_match)
            if update_reason:
                _mark_material_update(item, update_reason)
                fresh.append(item)
            else:
                duplicates += 1
            continue

        # 不同项目也可能连续几天只是重复同一种机会。只在明确场景和高语义相似时抑制。
        if category != "policy":
            fatigue_match = next(
                (
                    previous
                    for previous in histories.get(category, [])
                    if _same_recent_opportunity(data, previous)
                ),
                None,
            )
            if fatigue_match is not None:
                _mark_opportunity_fatigue(item, fatigue_match)
                duplicates += 1
                fatigue_duplicates += 1
                continue

        # 防止非常旧、已超出语义回看窗口的同 URL 再次触发唯一键冲突。
        url = str(data.get("url") or "").strip()
        if url and exists(db, url):
            duplicates += 1
            continue

        fresh.append(item)

    if fatigue_duplicates:
        logger.info(
            "跨天机会疲劳抑制：输入=%s 抑制=%s 窗口=%s天",
            len(rows),
            fatigue_duplicates,
            OPPORTUNITY_FATIGUE_DAYS,
        )
    return fresh, duplicates