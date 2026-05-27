from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from ..auth import current_user_optional, other_user
from ..db import get_db
from ..models import CreativePost, Goal, Habit, User
from ..stats import (
    ensure_entries_for, get_or_create_today, goal_progress_summary,
    streak, weekly_pct,
)
from ..templating import templates
from ..time_utils import today_for


router = APIRouter()


def _column_for(db: OrmSession, user: User, today):
    habits = (
        db.query(Habit)
        .filter(Habit.user_id == user.id, Habit.status == "active")
        .order_by(Habit.position, Habit.id)
        .all()
    )
    ci = get_or_create_today(db, user)
    ensure_entries_for(db, ci, habits)
    entries_by_habit = {e.habit_id: e for e in ci.entries}
    rows = []
    done_count = 0
    for h in habits:
        e = entries_by_habit.get(h.id)
        if e and e.state == "done":
            done_count += 1
        rows.append({"habit": h, "entry": e})

    goals = (
        db.query(Goal)
        .filter(Goal.user_id == user.id, Goal.status == "active")
        .order_by(Goal.category, Goal.id)
        .all()
    )
    goals_data = [{
        "goal": g,
        "summary": goal_progress_summary(g),
    } for g in goals]
    return {
        "user": user,
        "rows": rows,
        "done_count": done_count,
        "habits_count": len(habits),
        "goals": goals_data,
        "streak": streak(db, user, today),
        "weekly_pct": weekly_pct(db, user, today),
        "checkin": ci,
        "today": today,
    }


@router.get("/")
def home(
    request: Request,
    user: User | None = Depends(current_user_optional),
    db: OrmSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    today_me = today_for(user)
    other = other_user(db, user)

    me_col = _column_for(db, user, today_me)
    other_col = _column_for(db, other, today_for(other)) if other else None

    posts = (
        db.query(CreativePost)
        .order_by(CreativePost.created_at.desc())
        .limit(8)
        .all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "other": other,
            "me_col": me_col,
            "other_col": other_col,
            "posts": posts,
        },
    )
