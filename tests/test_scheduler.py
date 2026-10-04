from types import SimpleNamespace

from app import scheduler as radar_scheduler


class FakeScheduler:
    def __init__(self):
        self.running = False
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append((func, trigger, kwargs))

    def start(self):
        self.running = True

    def shutdown(self, wait=False):
        self.running = False


def test_scheduler_registers_prep_and_primary_publish_jobs(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr(radar_scheduler, "scheduler", fake)

    radar_scheduler.start_scheduler()

    assert fake.running is True
    assert len(fake.jobs) == 2
    jobs = {row[2]["id"]: row for row in fake.jobs}

    prep = jobs["prepare_local_fallback"][2]
    publish = jobs["publish_daily_radar"][2]

    assert prep["hour"] == radar_scheduler.PREP_HOUR
    assert prep["minute"] == radar_scheduler.PREP_MINUTE
    assert prep["misfire_grace_time"] == 20 * 60
    assert publish["hour"] == radar_scheduler.RUN_HOUR
    assert publish["minute"] == radar_scheduler.RUN_MINUTE
    assert publish["misfire_grace_time"] == 10 * 60


def test_prepare_fallback_job_runs_without_publish(monkeypatch):
    calls = []
    monkeypatch.setattr(
        radar_scheduler,
        "prepare_local_fallback",
        lambda: calls.append("prepare") or {"status": "prepared", "cards": 3},
    )

    radar_scheduler.prepare_fallback_job()

    assert calls == ["prepare"]


def test_publish_job_enforces_0800_window(monkeypatch):
    calls = []
    monkeypatch.setenv("RADAR_ENFORCE_SEND_WINDOW", "0")
    monkeypatch.setenv("RADAR_SEND_WINDOW_START", "00:00")
    monkeypatch.setenv("RADAR_SEND_WINDOW_END", "23:59")
    monkeypatch.setattr(
        radar_scheduler,
        "publish_daily_feed",
        lambda: calls.append("publish") or 0,
    )
    recorded = []
    monkeypatch.setattr(
        radar_scheduler,
        "_record_scheduler_publish",
        lambda exit_code: recorded.append(exit_code),
    )

    radar_scheduler.publish_radar_job()

    assert calls == ["publish"]
    assert recorded == [0]
    assert radar_scheduler.os.environ["RADAR_ENFORCE_SEND_WINDOW"] == "1"
    assert radar_scheduler.os.environ["RADAR_SEND_WINDOW_START"] == "08:00"
    assert radar_scheduler.os.environ["RADAR_SEND_WINDOW_END"] == "08:10"


def test_publish_job_does_not_raise_when_publisher_fails(monkeypatch):
    monkeypatch.setattr(radar_scheduler, "publish_daily_feed", lambda: 1)
    recorded = []
    monkeypatch.setattr(
        radar_scheduler,
        "_record_scheduler_publish",
        lambda exit_code: recorded.append(exit_code),
    )

    radar_scheduler.publish_radar_job()

    assert recorded == [1]
