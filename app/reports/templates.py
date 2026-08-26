def build_daily_report(items):
    lines = ["🔥 AI 情报雷达日报", ""]

    for index, item in enumerate(items[:10], start=1):
        lines.append(f"{index}. {item.get('title', '未知项目')}")
        lines.append(f"热度分：{item.get('score', item.get('trend_score', 0))}")
        lines.append(item.get("summary", ""))
        lines.append("")

    return "\n".join(lines)
