#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.cards import build_daily_cards
from app.config import REPORT_TIMEZONE
from app.pipeline import (
    build_decision_model,
    collect_policies,
    collect_sources,
    select_policy_candidates,
    select_project_candidates,
)
DEFAULT_OUTPUT = Path("data/local-fallback-cards.json")


def _today() -> str:
    return datetime.now(ZoneInfo(REPORT_TIMEZONE)).date().isoformat()


def _score_level(value: float) -> str:
    score = float(value or 0)
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _project_analysis(item) -> dict:
    metrics = item.metrics or {}
    selection_score = float(metrics.get("selection_score") or item.trend_score or 0)
    description = " ".join(str(item.description or "").split()).strip()
    title = str(item.title or "未命名项目").strip()
    tags = [str(x) for x in metrics.get("priority_tags") or []]
    if tags:
        direction = f"先验证 {title} 在“{tags[0]}”场景中的真实可执行性与集成成本。"
    else:
        direction = f"先查看 {title} 原始项目，验证真实能力、维护活跃度与接入成本。"

    return {
        "purpose": description or f"{title} 的公开项目说明。",
        "summary": "本地兜底筛选已通过时效、相关性和增长门槛；建议以原始项目证据继续验证。",
        "business_score": max(min(selection_score, 100), 0),
        "opportunity": _score_level(selection_score),
        "startup_ideas": [direction],
        "llm_meta": {
            "success": False,
            "fallback": True,
            "reason": "07:35 预生成确定性本地兜底",
        },
    }


def _policy_analysis(item) -> dict:
    metrics = item.metrics or {}
    policy_score = float(metrics.get("policy_score") or 50)
    title = str(item.title or "美国合规更新").strip()
    description = " ".join(str(item.description or "").split()).strip()
    action = f"查看 {title} 官方原文，确认适用产品、时间节点与现有资料缺口。"

    return {
        "purpose": description or f"{title} 的官方更新。",
        "summary": "本地兜底已采集到官方来源更新；执行前应以官方原文确认适用范围。",
        "affected_products": "需依据官方原文确认具体适用产品、功能特征与豁免范围。",
        "risk": "若适用范围判断错误，可能造成准入、下架、召回或进口合规风险。",
        "preparation": "保存官方原文，并核对测试、证书、注册、标签、申报和供应商批次资料。",
        "business_score": max(min(policy_score, 100), 0),
        "opportunity": _score_level(policy_score),
        "startup_ideas": [action],
        "llm_meta": {
            "success": False,
            "fallback": True,
            "reason": "07:35 预生成确定性本地兜底",
        },
    }


def prepare(output_path: Path | None = None) -> dict:
    date_text = str(os.getenv("CHATGPT_FEED_DATE") or _today()).strip()
    target = output_path or Path(
        os.getenv("RADAR_LOCAL_FALLBACK_PATH") or str(DEFAULT_OUTPUT)
    )

    target.parent.mkdir(parents=True, exist_ok=True)

    # 无论 ChatGPT Feed 是否已经存在，都预生成一份当天确定性兜底。
    # 这样 08:00 即使 GitHub API 临时不可达，发布器仍有可发送内容。
    projects = select_project_candidates(collect_sources())[:5]
    policies = select_policy_candidates(collect_policies())[:3]

    for item in projects:
        item.analysis = _project_analysis(item)
    for item in policies:
        item.analysis = _policy_analysis(item)

    if not projects and not policies:
        raise RuntimeError("本地兜底未采集到可发送项目或合规情报")

    model = build_decision_model(projects, policies)
    cards = build_daily_cards(model)

    record = {
        "version": 1,
        "date": date_text,
        "source": "local_deterministic_fallback",
        "generated_at": datetime.now(ZoneInfo(REPORT_TIMEZONE)).isoformat(),
        "cards": [asdict(card) for card in cards],
    }
    payload = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    result = {
        "status": "prepared",
        "date": date_text,
        "cards": len(cards),
        "projects": len(projects),
        "policies": len(policies),
        "path": str(target),
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> int:
    try:
        prepare()
        return 0
    except Exception as exc:
        print(f"本地 Radar 兜底准备失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
