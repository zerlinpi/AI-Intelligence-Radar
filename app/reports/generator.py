from datetime import datetime


def generate_daily_report(items):
    lines = [
        "🔥 AI Intelligence Radar Daily",
        datetime.utcnow().strftime('%Y-%m-%d'),
        ""
    ]

    for index, item in enumerate(items[:10], 1):
        lines.append(
            f"{index}. {item.get('title')}\n"
            f"Score: {item.get('score', 0)}\n"
            f"{item.get('description','')[:150]}\n"
        )

    return "\n".join(lines)
