from datetime import datetime, timedelta, date

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .db import SessionLocal
from .models import CheckIn, CheckInEntry, User
from .time_utils import today_for, user_tz, is_within_grace


_scheduler: BackgroundScheduler | None = None


def _rollover_tick():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for u in users:
            today = today_for(u)
            # Find all check-ins for this user older than today; finalize pending entries
            old_checkins = (
                db.query(CheckIn)
                .filter(CheckIn.user_id == u.id, CheckIn.date < today, CheckIn.locked == False)  # noqa: E712
                .all()
            )
            for ci in old_checkins:
                if is_within_grace(ci.date, u):
                    continue
                for e in ci.entries:
                    if e.state == "pending":
                        e.state = "missed"
                ci.locked = True
        db.commit()
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_rollover_tick, "interval", hours=1, next_run_time=datetime.utcnow() + timedelta(seconds=10))
    _scheduler.start()


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
