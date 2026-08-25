from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(
        daily_radar_job,
        "cron",
        hour=8,
        minute=0
    )
    scheduler.start()


def daily_radar_job():
    print("Running AI Intelligence Radar daily pipeline")
