from threading import RLock
from typing import Dict


# 生产主流程固定会运行这些采集器。只有同一轮已经收齐全部基础健康记录时，
# 才把覆盖状态用于飞书提示，避免单元测试/独立调用某个采集器时产生陈旧告警。
EXPECTED_SOURCES = {
    "github",
    "hackernews",
    "huggingface",
    "arxiv",
    "producthunt",
    "policy",
}

SOURCE_LABELS = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
    "policy": "美国合规政策",
}

_lock = RLock()
_health: Dict[str, Dict] = {}


def reset_collection_health() -> None:
    """清空本进程的采集覆盖快照。主要供测试和显式运维调用使用。"""
    with _lock:
        _health.clear()


def record_collector_health(source: str, health: Dict) -> None:
    """记录采集器最近一次 collect_safe 的健康状态。

    GitHub 是生产 COLLECTORS 的第一个来源，因此其新一轮状态到来时清空上一轮快照，
    防止长驻 Scheduler 把昨天的失败状态带进今天的卡片。
    """
    key = str(source or "unknown").strip().lower() or "unknown"
    snapshot = dict(health or {})
    with _lock:
        if key == "github":
            _health.clear()
        _health[key] = snapshot


def collector_health_snapshot() -> Dict[str, Dict]:
    with _lock:
        return {key: dict(value) for key, value in _health.items()}


def coverage_snapshot() -> Dict:
    """汇总当前一轮数据覆盖状态。

    success=True 但 result_count=0 表示“成功查询但没有新内容”，不是故障；
    available=False 表示来源因缺少配置/权限根本没有执行，同样不能解释为“没有新内容”。
    """
    health = collector_health_snapshot()
    if not EXPECTED_SOURCES.issubset(set(health)):
        return {
            "available": False,
            "complete": True,
            "project_complete": True,
            "policy_complete": True,
            "project_failed": [],
            "project_unavailable": [],
            "policy_failed": [],
            "policy_degraded": [],
            "note": "",
        }

    project_sources = ("github", "hackernews", "huggingface", "arxiv", "producthunt")
    project_unavailable = [
        SOURCE_LABELS.get(source, source)
        for source in project_sources
        if (health.get(source) or {}).get("available") is False
    ]
    project_failed = [
        SOURCE_LABELS.get(source, source)
        for source in project_sources
        if not bool((health.get(source) or {}).get("success"))
        and (health.get(source) or {}).get("available") is not False
    ]

    policy_health = health.get("policy") or {}
    policy_sources = policy_health.get("policy_sources") or {}
    if not isinstance(policy_sources, dict):
        policy_sources = {}

    policy_failed = [str(value) for value in (policy_sources.get("failed_authorities") or [])]
    policy_degraded = [str(value) for value in (policy_sources.get("degraded_authorities") or [])]

    # 如果整个 PolicyCollector 自身失败，机构级状态可能是上一轮残留或根本不存在；
    # 此时只使用主采集器失败这一事实。
    if not bool(policy_health.get("success")):
        policy_failed = ["美国合规政策采集"]
        policy_degraded = []

    project_complete = not project_failed and not project_unavailable
    policy_complete = not policy_failed and not policy_degraded
    complete = project_complete and policy_complete

    parts = []
    if project_unavailable:
        parts.append("项目源不可用：" + "、".join(project_unavailable))
    if project_failed:
        parts.append("项目源失败：" + "、".join(project_failed))
    if policy_failed:
        parts.append("政策覆盖失败：" + "、".join(policy_failed))
    if policy_degraded:
        parts.append("政策查询部分降级：" + "、".join(policy_degraded))

    note = "；".join(parts)
    if note:
        note = f"数据覆盖不完整：{note}。当前结论仅基于本轮成功获取的来源，不能把缺失数据解释为“没有变化”。"

    return {
        "available": True,
        "complete": complete,
        "project_complete": project_complete,
        "policy_complete": policy_complete,
        "project_failed": project_failed,
        "project_unavailable": project_unavailable,
        "policy_failed": policy_failed,
        "policy_degraded": policy_degraded,
        "note": note,
    }
