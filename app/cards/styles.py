SUMMARY_HEADER_TEMPLATE = "turquoise"
PRODUCT_HEADER_TEMPLATE = "blue"
DAILY_HEADER_TEMPLATE = SUMMARY_HEADER_TEMPLATE
DECISION_BACKGROUND = "grey"

# 合规卡 Header 根据当日最高风险动态变化；正文仍使用文字 + Emoji 明确标注风险，
# 颜色只做视觉辅助，不作为唯一风险信号。
COMPLIANCE_HEADER_TEMPLATES = {
    "high": "red",
    "medium": "orange",
    "low": "turquoise",
}

# 这是信息架构数量限制，不是文案长度限制。
# Top Actions 固定最多 3 条；产品每页优先放 5 项，超出后继续分页，不丢弃内容。
MAX_ACTIONS = 3
DEFAULT_PROJECTS_PER_CARD = 5

RISK_LABELS = {
    "high": "🔴 高风险",
    "medium": "🟠 中风险",
    "low": "🟢 低风险",
}

OPPORTUNITY_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

FOCUS_TITLES = {
    "Amazon政策与审核": "A｜Amazon 政策与审核",
    "美国跨境新规": "B｜美国跨境进口新规",
    "产品合规审核": "C｜美国市场产品审核",
}
