from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

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
    return {
        "正常": True,
        "调度器运行中": bool(scheduler.running),
    }


@app.get("/ready")
def readiness_check():
    ready = bool(scheduler.running)
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "就绪": ready,
            "调度器运行中": ready,
        },
    )


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
        "是否跳过": bool(result.get("skipped", False)),
        "原因": result.get("reason", ""),
        "项目": [_public_item(item) for item in result.get("items", [])],
    }


@app.post("/run")
def run():
    return _public_result(run_daily_radar())
