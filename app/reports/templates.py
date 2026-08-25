def build_daily_report(items):
    lines = ["🔥 AI Intelligence Radar Daily", ""]

    for index, item in enumerate(items[:10], start=1):
        lines.append(f"{index}. {item.get('title', 'Unknown')}")
        lines.append(f"Score: {item.get('score', 0)}")
        lines.append(item.get('summary', ''))
        lines.append("")

    return "\n".join(lines)
