import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

from app.cards.models import CardEnvelope
from app.config import FEISHU_OUTBOX_DIR


_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    cleaned = _SAFE_ID.sub("-", str(value or "run")).strip("-._")
    return cleaned[:96] or "run"


def _outbox_dir() -> Path:
    path = Path(FEISHU_OUTBOX_DIR).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, data: dict) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(directory),
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


def queue_cards(run_id: str, cards: Iterable[CardEnvelope]) -> Path:
    """在真正发送前持久化整组卡片，确保进程重启后可继续补发。"""
    directory = _outbox_dir()
    path = directory / f"{_safe_id(run_id)}.json"

    if path.exists():
        # 同一个 run_id 已经入队时绝不覆盖现有发送进度。
        return path

    serialized = []
    for raw_card in list(cards or []):
        card = raw_card if isinstance(raw_card, CardEnvelope) else CardEnvelope(**raw_card)
        serialized.append(
            {
                "card_type": str(card.card_type or "unknown"),
                "payload": card.payload if isinstance(card.payload, dict) else {},
                "fallback_text": str(card.fallback_text or ""),
                "sent": False,
                "sent_at": None,
            }
        )

    record = {
        "version": 1,
        "run_id": str(run_id or ""),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "cards": serialized,
    }
    _atomic_write(path, record)
    return path


def list_pending() -> List[Path]:
    directory = _outbox_dir()
    return sorted(
        (path for path in directory.glob("*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )


def load_record(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ValueError(f"无效飞书发送队列文件：{path}")
    return data


def pending_cards(path: Path) -> List[Tuple[int, CardEnvelope]]:
    data = load_record(path)
    result: List[Tuple[int, CardEnvelope]] = []
    for index, row in enumerate(data.get("cards") or []):
        if not isinstance(row, dict) or row.get("sent") is True:
            continue
        result.append(
            (
                index,
                CardEnvelope(
                    card_type=str(row.get("card_type") or "unknown"),
                    payload=row.get("payload") if isinstance(row.get("payload"), dict) else {},
                    fallback_text=str(row.get("fallback_text") or ""),
                ),
            )
        )
    return result


def mark_sent(path: Path, index: int) -> bool:
    data = load_record(path)
    cards = data.get("cards") or []
    if index < 0 or index >= len(cards):
        raise IndexError(index)

    row = cards[index]
    if not isinstance(row, dict):
        raise ValueError(f"无效发送队列条目：{path}#{index}")
    row["sent"] = True
    row["sent_at"] = _utc_now()
    data["updated_at"] = _utc_now()
    _atomic_write(Path(path), data)

    complete = all(isinstance(card, dict) and card.get("sent") is True for card in cards)
    if complete:
        Path(path).unlink(missing_ok=True)
    return complete


def quarantine(path: Path) -> Path:
    """损坏队列不反复阻塞每次日报，移入 bad 子目录等待人工检查。"""
    source = Path(path)
    bad_dir = _outbox_dir() / "bad"
    bad_dir.mkdir(parents=True, exist_ok=True)
    target = bad_dir / source.name
    if target.exists():
        target = bad_dir / f"{source.stem}-{int(datetime.now().timestamp())}.json"
    os.replace(source, target)
    return target
