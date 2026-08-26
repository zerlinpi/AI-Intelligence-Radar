import sys

from app.core.outbox import list_pending
from app.core.preflight import run_preflight
from app.core.run_history import latest_run, record_run_safe
from app.database.backup import list_backups
from app.feishu import flush_feishu_outbox
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


def status():
    """展示最近执行、待补发飞书队列与数据库备份状态，不访问外部 API。"""
    last = latest_run()
    pending = list_pending()
    backups = list_backups()

    if last:
        print(
            "最近执行："
            f"状态={last.get('status', 'unknown')} "
            f"执行编号={last.get('execution_id') or '-'} "
            f"项目={last.get('item_count', 0)} "
            f"政策={last.get('policy_count', 0)} "
            f"保存={last.get('saved_count', 0)} "
            f"AI降级={last.get('ai_fallbacks', 0)} "
            f"飞书={last.get('feishu_sent', False)} "
            f"耗时={last.get('duration', 0)}秒"
        )
        for error in last.get("errors") or []:
            print(f"[异常] {error}")
    else:
        print("最近执行：暂无持久化运行历史")

    print(f"飞书待补发队列：{len(pending)}")
    if pending:
        print(f"最早待补发：{pending[0]}")

    print(f"数据库备份：{len(backups)}")
    if backups:
        print(f"最新备份：{backups[0]}")
    return True


def flush():
    """只补发飞书持久化队列，不重新采集、不调用 DeepSeek。"""
    ok = flush_feishu_outbox()
    print("飞书待发送队列已全部补发。" if ok else "飞书队列仍有未完成项目，请查看日志。")
    return ok


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
        f"状态={result.get('status', 'unknown')} "
        f"项目数量={len(result.get('items', []))} "
        f"政策数量={len(result.get('policies', []))} "
        f"飞书卡片={result.get('feishu_cards', 0)} "
        f"耗时={result.get('duration', 0)}秒"
    )


def main():
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "run"

    if command == "check":
        return 0 if check() else 1
    if command == "status":
        return 0 if status() else 1
    if command == "flush":
        return 0 if flush() else 1
    if command not in {"run", "日报"}:
        print("未知命令。可用：run | check | status | flush")
        return 2

    # run_daily_radar 内部自带 execution_lock + preflight，避免 CLI 与生产路径出现两套规则。
    result = run_daily_radar()
    record_run_safe(result)
    _print_run_summary(result)

    if not isinstance(result, dict):
        return 1
    if result.get("skipped"):
        return 0
    status_value = str(result.get("status") or "success").lower()
    return 0 if status_value == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
