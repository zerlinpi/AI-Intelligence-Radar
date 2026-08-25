from apscheduler.schedulers.background import BackgroundScheduler

from app.pipeline import run_daily_radar

scheduler = BackgroundScheduler()


def daily_radar_job():
    try:
        run_daily_radar()
    except Exception as error:
        print(f"daily radar failed: {error}")


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        daily_radar_job,
        "cron",
        hour=8,
        minute=0,
        id="daily_radar",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
