import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.config import RUN_HISTORY_FILE, RUN_HISTORY_LIMIT
from app.core.logger import get_logger


logger = get_logger("运行历史")
_FALLBACK_PATTERN = re.compile(r"AI 分析降级\s*(\d+)\s*条")


def _history_path() -> Path:
    path = Path(RUN_HISTORY_FILE).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, data) -> None:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _read_all() -> List[Dict]:
    path = _history_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _infer_fallback_count(errors) -> int:
    for error in errors or []:
        match = _FALLBACK_PATTERN.search(str(error))
        if match:
            return int(match.group(1))
    return 0


def _summary(result: Dict) -> Dict:
    result = result if isinstance(result, dict) else {}
    errors = [str(item) for item in (result.get("errors") or [])[:20]]
    item_count = len(result.get("items") or [])
    policy_count = len(result.get("policies") or [])
    ai_fallbacks = int(result.get("ai_fallbacks") or _infer_fallback_count(errors))

    raw_saved = result.get("saved_count")
    if raw_saved is None:
        has_database_error = any("数据库保存" in error for error in errors)
        saved_count = 0 if has_database_error else max(item_count + policy_count - ai_fallbacks, 0)
    else:
        saved_count = int(raw_saved or 0)

    return {
        "execution_id": str(result.get("execution_id") or ""),
        "time": str(result.get("time") or datetime.now(timezone.utc).isoformat()),
        "duration": float(result.get("duration") or 0),
        "status": str(result.get("status") or "unknown"),
        "item_count": item_count,
        "policy_count": policy_count,
        "saved_count": saved_count,
        "ai_fallbacks": ai_fallbacks,
        "feishu_cards": int(result.get("feishu_cards") or 0),
        "feishu_sent": bool(result.get("feishu_sent", False)),
        "skipped": bool(result.get("skipped", False)),
        "reason": str(result.get("reason") or ""),
        "errors": errors,
    }


def record_run(result: Dict) -> Dict:
    """保存轻量执行摘要；不写入完整项目内容、URL 或密钥。"""
    path = _history_path()
    history = _read_all()
    row = _summary(result)
    history.append(row)
    keep = max(int(RUN_HISTORY_LIMIT or 100), 10)
    _atomic_write(path, history[-keep:])
    return row


def record_run_safe(result: Dict) -> Optional[Dict]:
    """运行历史属于可观测性能力；写入失败不应覆盖日报真实执行结果。"""
    try:
        return record_run(result)
    except Exception:
        logger.exception("保存运行历史失败")
        return None


def recent_runs(limit: int = 10) -> List[Dict]:
    rows = _read_all()
    count = max(int(limit or 1), 1)
    return list(reversed(rows[-count:]))


def latest_run() -> Optional[Dict]:
    rows = _read_all()
    return rows[-1] if rows else None
