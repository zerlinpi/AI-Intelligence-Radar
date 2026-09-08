#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import requests

from app.cards import build_daily_cards
from app.chatgpt_feed import report_model_from_dict
from app.config import REPORT_TIMEZONE
from app.feishu import send_feishu_cards


MARKER = "AI-INTELLIGENCE-RADAR-CHATGPT-FEED"
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
STATUS_PATH = Path("data/chatgpt-feed-status.json")


def extract_report_from_comment(body: str) -> Optional[Dict[str, Any]]:
    text = str(body or "")
    if MARKER not in text:
        return None
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _today() -> str:
    return datetime.now(ZoneInfo(REPORT_TIMEZONE)).date().isoformat()


def fetch_latest_report(
    repository: str,
    issue_number: int,
    token: str,
    expected_date: str,
) -> Dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments"
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params={"per_page": 100, "sort": "created", "direction": "desc"},
        timeout=20,
    )
    response.raise_for_status()
    comments = response.json()
    if not isinstance(comments, list):
        raise RuntimeError("GitHub Issue comments response is not a list")

    stale_dates = []
    for comment in reversed(comments):
        payload = extract_report_from_comment(comment.get("body", ""))
        if payload is None:
            continue
        report_date = str(payload.get("date_text") or "").strip()
        if report_date == expected_date:
            return payload
        if report_date:
            stale_dates.append(report_date)

    stale_hint = ", ".join(sorted(set(stale_dates), reverse=True)[:3])
    detail = f"；最近可见日期={stale_hint}" if stale_hint else ""
    raise RuntimeError(f"未找到 {expected_date} 的 ChatGPT Radar Feed{detail}")


def _write_status(**data: Any) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    repository = str(os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = str(os.getenv("GITHUB_TOKEN") or "").strip()
    issue_number = int(os.getenv("CHATGPT_FEED_ISSUE", "2"))
    expected_date = str(os.getenv("CHATGPT_FEED_DATE") or _today()).strip()

    if not repository:
        raise RuntimeError("缺少 GITHUB_REPOSITORY")
    if not token:
        raise RuntimeError("缺少 GITHUB_TOKEN")

    try:
        payload = fetch_latest_report(
            repository=repository,
            issue_number=issue_number,
            token=token,
            expected_date=expected_date,
        )
        model = report_model_from_dict(payload)
        cards = build_daily_cards(model)
        card_types = [card.card_type for card in cards]

        sent = send_feishu_cards(
            cards,
            run_id=f"chatgpt-feed-{expected_date}",
            durable=True,
        )
        _write_status(
            date=expected_date,
            issue=issue_number,
            cards=len(cards),
            card_types=card_types,
            sent=bool(sent),
            status="success" if sent else "failed",
        )
        print(
            f"ChatGPT Radar Feed：date={expected_date} issue=#{issue_number} "
            f"cards={len(cards)} sent={sent}"
        )
        return 0 if sent else 1
    except Exception as exc:
        _write_status(
            date=expected_date,
            issue=issue_number,
            cards=0,
            sent=False,
            status="failed",
            error=str(exc),
        )
        print(f"ChatGPT Radar Feed 发送失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
