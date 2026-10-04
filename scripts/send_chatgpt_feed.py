#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import requests

from app.cards import build_daily_cards
from app.cards.models import CardEnvelope
from app.chatgpt_feed import report_model_from_dict
from app.config import REPORT_TIMEZONE
from app.feishu import send_feishu, send_feishu_cards


MARKER = "AI-INTELLIGENCE-RADAR-CHATGPT-FEED"
DELIVERY_MARKER = "AI-INTELLIGENCE-RADAR-DELIVERED"
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
STATUS_PATH = Path("data/chatgpt-feed-status.json")
_MAX_COMMENT_PAGES = 20


class MissingFeedError(RuntimeError):
    pass


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


def _parse_clock(value: str, default_hour: int, default_minute: int) -> tuple[int, int]:
    text = str(value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (TypeError, ValueError):
        pass
    return default_hour, default_minute


def _send_window_state(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(ZoneInfo(REPORT_TIMEZONE))
    start_hour, start_minute = _parse_clock(
        os.getenv("RADAR_SEND_WINDOW_START", "08:00"), 8, 0
    )
    end_hour, end_minute = _parse_clock(
        os.getenv("RADAR_SEND_WINDOW_END", "08:10"), 8, 10
    )
    start = current.replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )
    end = current.replace(
        hour=end_hour, minute=end_minute, second=0, microsecond=0
    )
    if current < start:
        return "early"
    if current >= end:
        return "late"
    return "open"


def _send_window_enforced() -> bool:
    return str(os.getenv("RADAR_ENFORCE_SEND_WINDOW") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _late_recovery_allowed() -> bool:
    return str(os.getenv("RADAR_ALLOW_LATE_RECOVERY") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _github_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_issue_comments(
    repository: str,
    issue_number: int,
    token: str,
) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments"
    comments: List[Dict[str, Any]] = []

    for page in range(1, _MAX_COMMENT_PAGES + 1):
        response = requests.get(
            url,
            headers=_github_headers(token),
            params={"per_page": 100, "page": page},
            timeout=20,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError("GitHub Issue comments response is not a list")
        comments.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return comments

    raise RuntimeError(
        f"Issue #{issue_number} 评论超过 {_MAX_COMMENT_PAGES * 100} 条，"
        "已达到 Radar 分页安全上限"
    )


def _comment_author(comment: Dict[str, Any]) -> str:
    user = comment.get("user")
    if not isinstance(user, dict):
        return ""
    return str(user.get("login") or "").strip()


def find_latest_report(
    comments: List[Dict[str, Any]],
    expected_date: str,
    trusted_author: str,
) -> Tuple[Dict[str, Any], int]:
    trusted = str(trusted_author or "").strip()
    if not trusted:
        raise RuntimeError("缺少 CHATGPT_FEED_AUTHOR")

    stale_dates = []
    for comment in reversed(comments):
        if _comment_author(comment).lower() != trusted.lower():
            continue
        payload = extract_report_from_comment(comment.get("body", ""))
        if payload is None:
            continue
        report_date = str(payload.get("date_text") or "").strip()
        if report_date == expected_date:
            comment_id = int(comment.get("id") or 0)
            if comment_id <= 0:
                raise RuntimeError("当天 ChatGPT Radar Feed 缺少有效 comment id")
            return payload, comment_id
        if report_date:
            stale_dates.append(report_date)

    stale_hint = ", ".join(sorted(set(stale_dates), reverse=True)[:3])
    detail = f"；可信作者最近可见日期={stale_hint}" if stale_hint else ""
    raise MissingFeedError(f"未找到 {expected_date} 的可信 ChatGPT Radar Feed{detail}")


def _receipt_payload(body: str) -> Optional[Dict[str, Any]]:
    text = str(body or "")
    if DELIVERY_MARKER not in text:
        return None
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def has_delivery_receipt(
    comments: List[Dict[str, Any]],
    expected_date: str,
    trusted_author: str,
) -> bool:
    allowed_authors = {
        str(trusted_author or "").strip().lower(),
        "github-actions[bot]",
    }
    allowed_authors.discard("")

    for comment in reversed(comments):
        if _comment_author(comment).lower() not in allowed_authors:
            continue
        payload = _receipt_payload(comment.get("body", ""))
        if payload is None:
            continue
        if str(payload.get("date_text") or "").strip() == expected_date:
            return True
    return False


def post_delivery_receipt(
    repository: str,
    issue_number: int,
    token: str,
    expected_date: str,
    feed_comment_id: int,
    cards: int,
    source: str = "chatgpt_feed",
) -> bool:
    url = f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments"
    body = (
        f"{DELIVERY_MARKER}\n\n"
        "```json\n"
        + json.dumps(
            {
                "date_text": expected_date,
                "feed_comment_id": int(feed_comment_id),
                "cards": int(cards),
                "source": str(source or "chatgpt_feed"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n```"
    )
    delays = (0, 5, 10, 20, 40, 60)
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        try:
            response = requests.post(
                url,
                headers=_github_headers(token),
                json={"body": body},
                timeout=20,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            print(
                f"GitHub delivery receipt 写入失败：attempt={attempt}/{len(delays)} "
                f"error={exc}",
                file=sys.stderr,
            )
    return False


def _read_status() -> Dict[str, Any]:
    if not STATUS_PATH.exists():
        return {}
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _already_sent(expected_date: str) -> bool:
    status = _read_status()
    return (
        str(status.get("date") or "") == expected_date
        and status.get("sent") is True
        and str(status.get("status") or "") == "success"
    )


def _alert_already_sent(expected_date: str, status_name: str) -> bool:
    status = _read_status()
    return (
        str(status.get("date") or "") == expected_date
        and str(status.get("status") or "") == status_name
        and status.get("alert_sent") is True
    )


def _write_status(**data: Any) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _send_alert(expected_date: str, message: str, status_name: str) -> bool:
    if _alert_already_sent(expected_date, status_name):
        return True
    text = (
        f"⚠️ AI 情报雷达 {expected_date}\n"
        f"{message}\n"
        "本次不会发送过期日报；请检查 GitHub Actions 与 Issue #2。"
    )
    try:
        return bool(send_feishu(text))
    except Exception:
        return False


def _load_local_fallback(expected_date: str) -> List[CardEnvelope]:
    path = Path(
        os.getenv("RADAR_LOCAL_FALLBACK_PATH")
        or "data/local-fallback-cards.json"
    )
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, dict):
        return []
    if str(data.get("date") or "").strip() != expected_date:
        return []
    if str(data.get("source") or "").strip() != "local_deterministic_fallback":
        return []

    result: List[CardEnvelope] = []
    for row in data.get("cards") or []:
        if not isinstance(row, dict):
            return []
        try:
            result.append(
                CardEnvelope(
                    card_type=str(row.get("card_type") or "fallback"),
                    payload=row.get("payload") if isinstance(row.get("payload"), dict) else {},
                    fallback_text=str(row.get("fallback_text") or ""),
                )
            )
        except Exception:
            return []
    return result


def _send_local_fallback(
    repository: str,
    issue_number: int,
    token: str,
    expected_date: str,
) -> bool:
    cards = _load_local_fallback(expected_date)
    if not cards:
        return False

    sent = send_feishu_cards(
        cards,
        run_id=f"local-fallback-{expected_date}",
        durable=True,
    )
    receipt_sent = False
    if sent:
        receipt_sent = post_delivery_receipt(
            repository=repository,
            issue_number=issue_number,
            token=token,
            expected_date=expected_date,
            feed_comment_id=0,
            cards=len(cards),
            source="local_deterministic_fallback",
        )

    _write_status(
        date=expected_date,
        issue=issue_number,
        cards=len(cards),
        card_types=[card.card_type for card in cards],
        sent=bool(sent),
        alert_sent=False,
        receipt_sent=bool(receipt_sent),
        status="success" if sent else "failed",
        source="local_deterministic_fallback",
    )
    print(
        f"Radar 本地兜底：date={expected_date} cards={len(cards)} "
        f"sent={sent} receipt_sent={receipt_sent}"
    )
    return bool(sent)


def main() -> int:
    repository = str(os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = str(os.getenv("GITHUB_TOKEN") or "").strip()
    trusted_author = str(os.getenv("CHATGPT_FEED_AUTHOR") or "").strip()
    issue_number = int(os.getenv("CHATGPT_FEED_ISSUE", "2"))
    expected_date = str(os.getenv("CHATGPT_FEED_DATE") or _today()).strip()

    if not repository:
        raise RuntimeError("缺少 GITHUB_REPOSITORY")
    if not token:
        raise RuntimeError("缺少 GITHUB_TOKEN")
    if not trusted_author:
        raise RuntimeError("缺少 CHATGPT_FEED_AUTHOR")

    if _already_sent(expected_date):
        print(f"ChatGPT Radar Feed：date={expected_date} 已成功发送，本轮跳过防止重复。")
        return 0

    try:
        # 先查 GitHub receipt，再判断发送窗口。
        # 多个早期唤醒任务中，第一轮发送成功后，后续排队任务即使 08:10 后才启动
        # 也应被视为“已完成”而不是误报失败。
        comments = fetch_issue_comments(
            repository=repository,
            issue_number=issue_number,
            token=token,
        )

        if has_delivery_receipt(comments, expected_date, trusted_author):
            _write_status(
                date=expected_date,
                issue=issue_number,
                cards=0,
                sent=True,
                status="success",
                deduplicated_by="github_delivery_receipt",
            )
            print(
                f"ChatGPT Radar Feed：date={expected_date} 已存在 GitHub delivery receipt，"
                "本轮跳过防止重复。"
            )
            return 0

        if _send_window_enforced():
            window_state = _send_window_state()
            allow_late = _late_recovery_allowed() and window_state == "late"
            if window_state != "open" and not allow_late:
                _write_status(
                    date=expected_date,
                    issue=issue_number,
                    cards=0,
                    sent=False,
                    alert_sent=False,
                    status="outside_send_window",
                    window_state=window_state,
                    window_start=os.getenv("RADAR_SEND_WINDOW_START", "08:00"),
                    window_end=os.getenv("RADAR_SEND_WINDOW_END", "08:10"),
                )
                print(
                    f"ChatGPT Radar Feed：date={expected_date} 当前不在北京时间发送窗口"
                    f"（state={window_state}），拒绝发送飞书。"
                )
                return 2
            if allow_late:
                print(
                    f"ChatGPT Radar Feed：date={expected_date} 已启用人工故障恢复，"
                    "允许本次 08:10 后补发。"
                )

        payload, feed_comment_id = find_latest_report(
            comments=comments,
            expected_date=expected_date,
            trusted_author=trusted_author,
        )
        model = report_model_from_dict(payload)
        cards = build_daily_cards(model)
        card_types = [card.card_type for card in cards]

        sent = send_feishu_cards(
            cards,
            run_id=f"chatgpt-feed-{expected_date}",
            durable=True,
        )
        alert_sent = False
        receipt_sent = False
        if sent:
            receipt_sent = post_delivery_receipt(
                repository=repository,
                issue_number=issue_number,
                token=token,
                expected_date=expected_date,
                feed_comment_id=feed_comment_id,
                cards=len(cards),
            )
        else:
            alert_sent = _send_alert(
                expected_date,
                "日报卡片未全部发送，可能存在飞书 Webhook、限流或历史 Outbox 阻塞。",
                "failed",
            )

        _write_status(
            date=expected_date,
            issue=issue_number,
            feed_comment_id=feed_comment_id,
            cards=len(cards),
            card_types=card_types,
            sent=bool(sent),
            alert_sent=bool(alert_sent),
            receipt_sent=bool(receipt_sent),
            status="success" if sent else "failed",
        )
        print(
            f"ChatGPT Radar Feed：date={expected_date} issue=#{issue_number} "
            f"cards={len(cards)} sent={sent} receipt_sent={receipt_sent} "
            f"alert_sent={alert_sent}"
        )
        return 0 if sent else 1
    except MissingFeedError as exc:
        if _send_local_fallback(
            repository=repository,
            issue_number=issue_number,
            token=token,
            expected_date=expected_date,
        ):
            print(
                f"ChatGPT Radar Feed 缺失：{exc}；已在 08:00 使用预生成本地兜底卡片。",
                file=sys.stderr,
            )
            return 0

        alert_sent = _send_alert(
            expected_date,
            "当天可信 ChatGPT Feed 缺失，且 07:35 本地兜底未生成或不可用。",
            "missing_feed",
        )
        _write_status(
            date=expected_date,
            issue=issue_number,
            cards=0,
            sent=False,
            alert_sent=bool(alert_sent),
            status="missing_feed",
            error=str(exc),
        )
        print(f"ChatGPT Radar Feed 缺失：{exc}；alert_sent={alert_sent}", file=sys.stderr)
        return 1
    except Exception as exc:
        # GitHub API 在 08:00 短暂不可达时，不应让飞书日报跟着失效。
        # 07:35 已经无条件准备当天本地兜底；优先使用它完成发送。
        if _send_local_fallback(
            repository=repository,
            issue_number=issue_number,
            token=token,
            expected_date=expected_date,
        ):
            print(
                f"ChatGPT Radar Feed 读取异常：{exc}；已使用预生成本地兜底卡片。",
                file=sys.stderr,
            )
            return 0

        alert_sent = _send_alert(
            expected_date,
            "日报发布发生异常，且预生成本地兜底不可用；已保留运行日志用于排查。",
            "failed",
        )
        _write_status(
            date=expected_date,
            issue=issue_number,
            cards=0,
            sent=False,
            alert_sent=bool(alert_sent),
            status="failed",
            error=str(exc),
        )
        print(f"ChatGPT Radar Feed 发送失败：{exc}；alert_sent={alert_sent}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
