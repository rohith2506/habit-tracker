from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import User
from .config import settings


def user_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def now_in_tz(user: User) -> datetime:
    return datetime.now(tz=user_tz(user))


def today_for(user: User) -> date:
    return now_in_tz(user).date()


def utc_to_local(dt: datetime, user: User) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(user_tz(user))


def local_midnight_utc(d: date, user: User) -> datetime:
    """UTC instant corresponding to local midnight of date d for user."""
    local = datetime.combine(d, datetime.min.time(), tzinfo=user_tz(user))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def is_within_grace(d: date, user: User) -> bool:
    """True if d's window (its day + grace hours into the next) is still open in the user's tz."""
    now_local = now_in_tz(user)
    end_local = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=user_tz(user)) + timedelta(hours=settings.grace_hours)
    return now_local <= end_local


def week_start(d: date) -> date:
    """Monday-based week start."""
    return d - timedelta(days=d.weekday())
