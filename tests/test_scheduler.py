from contextlib import contextmanager
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
    monkeypatch.setattr(radar_scheduler, "_startup_recovery_mode", lambda now=None: "")

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
    monkeypatch.setattr(radar_scheduler, "_fallback_ready_for_today", lambda now=None: True)
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
    assert radar_scheduler.os.environ["RADAR_PUBLISH_ROLE"] == "primary"
    assert radar_scheduler.os.environ["RADAR_ENFORCE_SEND_WINDOW"] == "1"
    assert radar_scheduler.os.environ["RADAR_SEND_WINDOW_START"] == "08:00"
    assert radar_scheduler.os.environ["RADAR_SEND_WINDOW_END"] == "08:10"


def test_publish_job_does_not_raise_when_publisher_fails(monkeypatch):
    monkeypatch.setattr(radar_scheduler, "_fallback_ready_for_today", lambda now=None: True)
    monkeypatch.setattr(radar_scheduler, "publish_daily_feed", lambda: 1)
    recorded = []
    monkeypatch.setattr(
        radar_scheduler,
        "_record_scheduler_publish",
        lambda exit_code: recorded.append(exit_code),
    )

    radar_scheduler.publish_radar_job()

    assert recorded == [1]



def test_publish_job_skips_when_cross_process_lock_is_held(monkeypatch):
    calls = []
    monkeypatch.setattr(radar_scheduler, "_fallback_ready_for_today", lambda now=None: True)

    @contextmanager
    def held_lock(path):
        yield False

    monkeypatch.setattr(radar_scheduler, "named_execution_lock", held_lock)
    monkeypatch.setattr(
        radar_scheduler,
        "publish_daily_feed",
        lambda: calls.append("publish") or 0,
    )

    radar_scheduler.publish_radar_job()

    assert calls == []


def test_publish_job_uses_configured_publish_lock(monkeypatch):
    seen = []
    monkeypatch.setattr(radar_scheduler, "_fallback_ready_for_today", lambda now=None: True)

    @contextmanager
    def free_lock(path):
        seen.append(path)
        yield True

    monkeypatch.setattr(radar_scheduler, "named_execution_lock", free_lock)
    monkeypatch.setattr(radar_scheduler, "publish_daily_feed", lambda: 0)
    monkeypatch.setattr(radar_scheduler, "_record_scheduler_publish", lambda exit_code: None)

    radar_scheduler.publish_radar_job()

    assert seen == [radar_scheduler.PUBLISH_LOCK_FILE]



def test_startup_recovery_mode_for_prepare_window():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")
    assert radar_scheduler._startup_recovery_mode(
        datetime(2026, 10, 5, 7, 40, tzinfo=tz)
    ) == "prepare"


def test_startup_recovery_mode_for_publish_window():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")
    assert radar_scheduler._startup_recovery_mode(
        datetime(2026, 10, 5, 8, 3, tzinfo=tz)
    ) == "publish"
    assert radar_scheduler._startup_recovery_mode(
        datetime(2026, 10, 5, 8, 10, tzinfo=tz)
    ) == ""


def test_scheduler_registers_startup_prepare_recovery(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr(radar_scheduler, "scheduler", fake)
    monkeypatch.setattr(radar_scheduler, "_startup_recovery_mode", lambda now=None: "prepare")

    radar_scheduler.start_scheduler()

    jobs = {row[2]["id"]: row for row in fake.jobs}
    assert "startup_recovery" in jobs
    assert jobs["startup_recovery"][0] is radar_scheduler.prepare_fallback_job
    assert jobs["startup_recovery"][1] == "date"


def test_scheduler_registers_startup_publish_recovery(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr(radar_scheduler, "scheduler", fake)
    monkeypatch.setattr(radar_scheduler, "_startup_recovery_mode", lambda now=None: "publish")

    radar_scheduler.start_scheduler()

    jobs = {row[2]["id"]: row for row in fake.jobs}
    assert "startup_recovery" in jobs
    assert jobs["startup_recovery"][0] is radar_scheduler.publish_radar_job
    assert jobs["startup_recovery"][1] == "date"


def test_publish_job_prepares_fallback_on_demand(monkeypatch):
    calls = []

    @contextmanager
    def free_lock(path):
        yield True

    monkeypatch.setattr(radar_scheduler, "named_execution_lock", free_lock)
    monkeypatch.setattr(radar_scheduler, "_fallback_ready_for_today", lambda now=None: False)
    monkeypatch.setattr(
        radar_scheduler,
        "prepare_fallback_job",
        lambda: calls.append("prepare"),
    )
    monkeypatch.setattr(
        radar_scheduler,
        "publish_daily_feed",
        lambda: calls.append("publish") or 0,
    )
    monkeypatch.setattr(radar_scheduler, "_record_scheduler_publish", lambda exit_code: None)

    radar_scheduler.publish_radar_job()

    assert calls == ["prepare", "publish"]
