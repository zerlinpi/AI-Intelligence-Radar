import sys

from app.core.preflight import run_preflight
from app.pipeline import run_daily_radar


def check():
    """只检查运行配置，不执行日报，也不调用外部付费 API。"""
    result = run_preflight()

    for item in result.checks:
        if item.required:
            level = "正常" if item.ok else "失败"
        else:
            level = "正常" if item.ok else "提醒"
        detail = f"：{item.detail}" if item.detail else ""
        print(f"[{level}] {item.name}{detail}")

    return result.ok


def _print_run_summary(result):
    if not isinstance(result, dict):
        print("日报执行结束，但没有返回有效结果。")
        return

    if result.get("skipped"):
        print(f"日报已跳过：{result.get('reason') or '已有任务正在运行'}")
        return

    print(
        "日报执行完成："
        f"执行编号={result.get('execution_id', '-')} "
        f"项目数量={len(result.get('items', []))} "
        f"政策数量={len(result.get('policies', []))} "
        f"飞书卡片={result.get('feishu_cards', 0)} "
        f"耗时={result.get('duration', 0)}秒"
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return 0 if check() else 1

    preflight = run_preflight()
    if not preflight.ok:
        print("日报未执行：生产预检失败。")
        for name in preflight.failures:
            print(f"[失败] {name}")
        return 2

    result = run_daily_radar()
    _print_run_summary(result)

    if not isinstance(result, dict):
        return 1
    if result.get("skipped"):
        return 0
    status = str(result.get("status") or "success").lower()
    return 0 if status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
