from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.outbox import list_pending
from app.core.preflight import run_preflight
from app.core.run_history import latest_run, record_run_safe
from app.database.backup import list_backups
from app.pipeline import run_daily_radar
from app.scheduler import start_scheduler, stop_scheduler, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="AI 情报雷达",
    lifespan=lifespan,
)

SOURCE_NAMES = {
    "github": "GitHub",
    "hackernews": "Hacker News",
    "huggingface": "Hugging Face",
    "arxiv": "arXiv",
    "producthunt": "Product Hunt",
}

METRIC_NAMES = {
    "stars": "星标",
    "forks": "分支",
    "open_issues": "待处理问题",
    "upvotes": "热度票",
    "comments": "评论",
    "downloads": "下载",
    "likes": "点赞",
    "momentum": "增长信号",
    "producthunt_url": "Product Hunt 链接",
    "website": "官方网站",
}


@app.get("/")
def home():
    return {
        "名称": "AI 情报雷达",
        "状态": "运行中",
    }


@app.get("/health")
def health_check():
    """Liveness：只证明进程还活着，不把外部配置问题误判为进程死亡。"""
    return {
        "正常": True,
        "调度器运行中": bool(scheduler.running),
    }


@app.get("/ready")
def readiness_check():
    """Readiness：调度器 + 本地生产预检均通过才允许接收执行请求。"""
    preflight = run_preflight()
    scheduler_ready = bool(scheduler.running)
    ready = scheduler_ready and preflight.ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "就绪": ready,
            "调度器运行中": scheduler_ready,
            "预检通过": preflight.ok,
            "失败项": preflight.failures,
        },
    )


@app.get("/status")
def runtime_status():
    """只返回轻量运行状态，不暴露密钥、Webhook 或完整项目内容。"""
    try:
        pending_count = len(list_pending())
    except Exception:
        pending_count = -1
    try:
        backup_count = len(list_backups())
    except Exception:
        backup_count = -1

    return {
        "调度器运行中": bool(scheduler.running),
        "最近执行": latest_run(),
        "飞书待补发队列": pending_count,
        "数据库备份数量": backup_count,
    }


def _public_metrics(metrics):
    if not isinstance(metrics, dict):
        return {}

    return {
        METRIC_NAMES.get(key, key): value
        for key, value in metrics.items()
    }


def _public_item(item):
    if not isinstance(item, dict):
        return {}

    analysis = item.get("analysis") or {}
    opportunity_map = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }

    source = str(item.get("source") or "")

    return {
        "项目名称": item.get("title", ""),
        "来源": SOURCE_NAMES.get(source, source),
        "链接": item.get("url", ""),
        "简介": item.get("description", ""),
        "上线时间": item.get("created_at"),
        "热度分": item.get("trend_score", 0),
        "指标": _public_metrics(item.get("metrics") or {}),
        "分析": {
            "摘要": analysis.get("summary", ""),
            "商业分": analysis.get("business_score", 0),
            "机会": opportunity_map.get(analysis.get("opportunity"), "中"),
            "机会点": analysis.get("startup_ideas") or [],
        },
    }


def _public_result(result):
    result = result if isinstance(result, dict) else {}
    return {
        "执行编号": result.get("execution_id", ""),
        "时间": result.get("time", ""),
        "耗时秒": result.get("duration", 0),
        "状态": result.get("status", "success"),
        "是否跳过": bool(result.get("skipped", False)),
        "原因": result.get("reason", ""),
        "错误": [str(item) for item in result.get("errors", [])],
        "项目": [_public_item(item) for item in result.get("items", [])],
        "政策": [_public_item(item) for item in result.get("policies", [])],
        "飞书卡片": result.get("feishu_cards", 0),
    }


def _is_preflight_failure(result) -> bool:
    if not isinstance(result, dict) or result.get("status") != "failed":
        return False
    return any("生产预检失败" in str(item) for item in result.get("errors", []))


@app.post("/run")
def run():
    # run_daily_radar 内部统一负责 execution_lock + preflight。
    result = run_daily_radar()
    record_run_safe(result)
    public = _public_result(result)
    if _is_preflight_failure(result):
        return JSONResponse(status_code=503, content=public)
    return public
