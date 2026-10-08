from datetime import datetime

from app.report_copy import project_display_description


def generate_daily_report(items):
    lines = [
        "🔥 AI 情报雷达日报",
        datetime.utcnow().strftime("%Y-%m-%d"),
        "",
    ]

    for index, item in enumerate(items[:10], 1):
        lines.append(
            f"{index}. {item.get('title')}\n"
            f"热度分：{item.get('score', item.get('trend_score', 0))}\n"
            f"{project_display_description(item.get('description', ''), source_name=item.get('source', ''))}\n"
        )

    return "\n".join(lines)
