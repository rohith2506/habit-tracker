from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .models import CheckIn, CheckInEntry, Habit, Goal, User
from .time_utils import today_for, week_start


def get_or_create_today(db: OrmSession, user: User) -> CheckIn:
    today = today_for(user)
    ci = (
        db.query(CheckIn)
        .filter(CheckIn.user_id == user.id, CheckIn.date == today)
        .one_or_none()
    )
    if ci is None:
        ci = CheckIn(user_id=user.id, date=today)
        db.add(ci)
        db.commit()
        db.refresh(ci)
    return ci


def ensure_entries_for(db: OrmSession, checkin: CheckIn, habits: Iterable[Habit]) -> list[CheckInEntry]:
    existing = {e.habit_id: e for e in checkin.entries}
    created = False
    for h in habits:
        if h.id not in existing:
            db.add(CheckInEntry(check_in_id=checkin.id, habit_id=h.id, state="pending"))
            created = True
    if created:
        db.commit()
        db.refresh(checkin)
    return checkin.entries


def cycle_state(state: str) -> str:
    return {"pending": "done", "done": "rest", "rest": "pending", "missed": "pending"}.get(state, "pending")


def weekly_count_for(db: OrmSession, user: User, habit: Habit, ref_date: date) -> int:
    ws = week_start(ref_date)
    we = ws + timedelta(days=6)
    q = (
        db.query(CheckInEntry)
        .join(CheckIn, CheckInEntry.check_in_id == CheckIn.id)
        .filter(
            CheckIn.user_id == user.id,
            CheckIn.date >= ws,
            CheckIn.date <= we,
            CheckInEntry.habit_id == habit.id,
            CheckInEntry.state == "done",
        )
    )
    return q.count()


def streak(db: OrmSession, user: User, today: date) -> int:
    """Consecutive days (ending today or yesterday) with ≥1 'done'.
    Rest days don't break the streak but don't count toward it; missed days break it."""
    count = 0
    # Walk back from today
    d = today
    # If today has any done, start counting today. Otherwise start from yesterday.
    while True:
        ci = (
            db.query(CheckIn)
            .filter(CheckIn.user_id == user.id, CheckIn.date == d)
            .one_or_none()
        )
        if ci is None:
            if d == today:
                d -= timedelta(days=1)
                continue
            break
        states = [e.state for e in ci.entries]
        if "missed" in states:
            break
        if "done" in states:
            count += 1
            d -= timedelta(days=1)
            continue
        # only rest/pending
        if "rest" in states:
            # neutral
            d -= timedelta(days=1)
            continue
        # all pending, nothing logged
        if d == today:
            d -= timedelta(days=1)
            continue
        break
    return count


def weekly_pct(db: OrmSession, user: User, today: date) -> int:
    """Average completion percentage across active habits for the current week.
    Daily habits: done / days-so-far-in-week. Weekly habits: min(1, done / weekly_target)."""
    ws = week_start(today)
    days_so_far = (today - ws).days + 1
    habits = (
        db.query(Habit)
        .filter(Habit.user_id == user.id, Habit.status == "active")
        .all()
    )
    if not habits:
        return 0
    fractions: list[float] = []
    for h in habits:
        done = weekly_count_for(db, user, h, today)
        if h.frequency == "daily":
            denom = max(1, days_so_far)
            fractions.append(min(1.0, done / denom))
        else:
            target = h.weekly_target or 1
            fractions.append(min(1.0, done / target))
    return round(100 * sum(fractions) / len(fractions))


def goal_progress_summary(goal: Goal) -> dict:
    """Latest value + pct toward target for a measurable goal."""
    if goal.kind != "measurable":
        return {"current": None, "pct": None, "delta": None}
    latest = None
    if goal.progress:
        latest = max(goal.progress, key=lambda p: p.logged_at).value
    if latest is None:
        latest = goal.start_value
    start, target = goal.start_value or 0.0, goal.target_value or 0.0
    span = target - start
    if span == 0:
        pct = 100 if (latest is not None and latest == target) else 0
    else:
        progressed = (latest - start) / span
        pct = round(100 * max(0.0, min(1.0, progressed)))
    return {"current": latest, "pct": pct, "delta": (latest - start) if latest is not None else 0}
