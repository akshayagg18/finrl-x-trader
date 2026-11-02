from datetime import datetime, timezone
import threading
import pandas as pd
import pandas_market_calendars as mcal

CAL = mcal.get_calendar("NYSE")


def schedule(start, end):
    return CAL.schedule(start_date=start, end_date=end)


def is_open(at=None):
    at = pd.Timestamp(at or datetime.now(timezone.utc))
    days = schedule(at.date(), at.date())
    return bool(
        len(days) and days.iloc[0].market_open <= at < days.iloc[0].market_close
    )


def next_operation(minutes=15, at=None):
    at = pd.Timestamp(at or datetime.now(timezone.utc))
    days = schedule(at.date(), (at + pd.Timedelta(days=14)).date())
    for _, row in days.iterrows():
        due = row.market_open + pd.Timedelta(minutes=minutes)
        if due > at:
            return due.isoformat()
    raise RuntimeError("Calendar has no upcoming session")


class Scheduler:
    def __init__(self, service):
        self.service = service
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(
            target=self.loop, daemon=True, name="finrl-scheduler"
        )
        self.thread.start()

    def tick(self, at=None):
        s = self.service.db.settings()
        db = self.service.db
        if not db.state("automation", False) or db.state("kill", False):
            return
        at = pd.Timestamp(at or datetime.now(timezone.utc))
        if not is_open(at):
            db.set_state(
                "next_operation",
                next_operation(s.automation.execution_minutes_after_open, at),
            )
            return
        days = schedule(at.date(), at.date())
        due = days.iloc[0].market_open + pd.Timedelta(
            minutes=s.automation.execution_minutes_after_open
        )
        if at < due:
            db.set_state("next_operation", due.isoformat())
            return
        # Service cycle key is session + scope; daily monitoring is separately idempotent.
        bucket = int(at.timestamp() // s.automation.monitor_seconds)
        try:
            self.service.cycle(
                scheduled=True,
                protect_only=db.state("paused", False),
                monitor_bucket=bucket,
            )
            db.set_state(
                "next_operation",
                (at + pd.Timedelta(seconds=s.automation.monitor_seconds)).isoformat(),
            )
        except Exception as exc:
            db.event(
                self.service.scope(),
                "scheduler_error",
                {
                    "error": type(exc).__name__,
                    "action": "No retry of uncertain orders; inspect audit",
                },
            )

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.service.db.event(
                    "system", "scheduler_error", {"error": type(exc).__name__}
                )
            self.stop_event.wait(10)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
