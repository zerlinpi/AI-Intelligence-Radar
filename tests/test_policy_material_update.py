from datetime import datetime, timedelta, timezone

from app.history_novelty import _policy_material_update_reason


def _policy(description, hours_offset=0):
    return {
        "category": "policy",
        "source": "amazon_policy",
        "title": "Product compliance documentation requirement",
        "description": description,
        "created_at": (datetime.now(timezone.utc) + timedelta(hours=hours_offset)).isoformat(),
        "metrics": {
            "policy_focus": "Amazon政策与审核",
            "policy_authority": "Amazon",
        },
    }


def test_reworded_same_policy_without_new_facts_is_not_material_update():
    previous = _policy(
        "Amazon sellers should review product compliance documentation before listing regulated items.",
        hours_offset=-24,
    )
    current = _policy(
        "Regulated listings need appropriate compliance documents and sellers should verify their files before publication.",
        hours_offset=0,
    )

    assert _policy_material_update_reason(current, previous) == ""


def test_changed_effective_date_is_material_update():
    previous = _policy(
        "The certification filing requirement takes effect 2026-09-01 for covered products.",
        hours_offset=-24,
    )
    current = _policy(
        "The certification filing requirement takes effect 2026-10-15 for covered products.",
        hours_offset=0,
    )

    reason = _policy_material_update_reason(current, previous)
    assert "日期" in reason or "阈值" in reason or "数值" in reason


def test_explicit_policy_revision_without_numbers_can_reenter():
    previous = _policy(
        "The program accepts existing compliance documentation through the normal seller review workflow.",
        hours_offset=-24,
    )
    current = _policy(
        "Amazon revised the program and now requires independent verification before a covered listing can be activated.",
        hours_offset=0,
    )

    reason = _policy_material_update_reason(current, previous)
    assert reason
    assert "修订" in reason or "新增要求" in reason
