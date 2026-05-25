from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from datetime import datetime

from ..auth import login_required
from ..blocks import ensure_active_block
from ..db import get_db
from ..models import Habit, User
from ..templating import templates


router = APIRouter()


HABIT_ICONS = [
    "ti-barbell", "ti-meat", "ti-moon", "ti-pencil", "ti-piano", "ti-palette",
    "ti-book", "ti-puzzle", "ti-run", "ti-glass-full", "ti-leaf", "ti-walk",
    "ti-coffee", "ti-yoga", "ti-music", "ti-camera", "ti-check",
]


def _opt_int(s: str | None) -> int | None:
    if s is None or s.strip() == "":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _my_habits(db: OrmSession, user: User, block_id: int) -> list[Habit]:
    return (
        db.execute(
            select(Habit)
            .where(Habit.user_id == user.id, Habit.block_id == block_id)
            .order_by(Habit.status == "active", Habit.position, Habit.id)
        )
        .scalars()
        .all()
    )


def _ctx(request: Request, db: OrmSession, user: User):
    block = ensure_active_block(db)
    habits = _my_habits(db, user, block.id)
    active = [h for h in habits if h.status == "active"]
    paused = [h for h in habits if h.status == "paused"]
    ended = [h for h in habits if h.status == "ended"]
    return {
        "request": request,
        "user": user,
        "block": block,
        "active_habits": active,
        "paused_habits": paused,
        "ended_habits": ended,
        "icons": HABIT_ICONS,
        "over_soft_cap": len(active) > 8,
    }


@router.get("/habits")
def page(request: Request, user: User = Depends(login_required), db: OrmSession = Depends(get_db)):
    return templates.TemplateResponse("habits.html", _ctx(request, db, user))


@router.post("/habits")
def create(
    request: Request,
    name: str = Form(...),
    icon: str = Form("ti-check"),
    frequency: str = Form("daily"),
    weekly_target: str | None = Form(None),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    block = ensure_active_block(db)
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    if frequency not in ("daily", "weekly"):
        frequency = "daily"
    wt = _opt_int(weekly_target)
    if frequency == "weekly":
        wt = max(1, min(6, wt or 3))
    else:
        wt = None
    # Position at end of active
    last_pos = db.query(Habit).filter(Habit.user_id == user.id, Habit.block_id == block.id).count()
    h = Habit(
        user_id=user.id, block_id=block.id,
        name=name, icon=icon if icon in HABIT_ICONS else "ti-check",
        frequency=frequency, weekly_target=wt,
        position=last_pos,
    )
    db.add(h)
    db.commit()
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/update")
def update(
    habit_id: int,
    name: str = Form(None),
    icon: str = Form(None),
    frequency: str = Form(None),
    weekly_target: str | None = Form(None),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    h = db.get(Habit, habit_id)
    if not h or h.user_id != user.id:
        raise HTTPException(404)
    if name is not None and name.strip():
        h.name = name.strip()
    if icon is not None and icon in HABIT_ICONS:
        h.icon = icon
    wt = _opt_int(weekly_target)
    if frequency in ("daily", "weekly"):
        h.frequency = frequency
        if frequency == "weekly":
            h.weekly_target = max(1, min(6, wt or h.weekly_target or 3))
        else:
            h.weekly_target = None
    db.commit()
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/pause")
def pause(habit_id: int, reason: str = Form(""), user: User = Depends(login_required), db: OrmSession = Depends(get_db)):
    h = db.get(Habit, habit_id)
    if not h or h.user_id != user.id:
        raise HTTPException(404)
    h.status = "paused"
    h.paused_at = datetime.utcnow()
    h.pause_reason = reason or None
    db.commit()
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/resume")
def resume(habit_id: int, user: User = Depends(login_required), db: OrmSession = Depends(get_db)):
    h = db.get(Habit, habit_id)
    if not h or h.user_id != user.id:
        raise HTTPException(404)
    h.status = "active"
    h.paused_at = None
    h.pause_reason = None
    db.commit()
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/end")
def end(habit_id: int, user: User = Depends(login_required), db: OrmSession = Depends(get_db)):
    h = db.get(Habit, habit_id)
    if not h or h.user_id != user.id:
        raise HTTPException(404)
    h.status = "ended"
    h.ended_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/delete")
def delete(habit_id: int, user: User = Depends(login_required), db: OrmSession = Depends(get_db)):
    h = db.get(Habit, habit_id)
    if not h or h.user_id != user.id:
        raise HTTPException(404)
    db.delete(h)
    db.commit()
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/move")
def move(
    habit_id: int,
    direction: str = Form(...),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    block = ensure_active_block(db)
    habits = (
        db.query(Habit)
        .filter(Habit.user_id == user.id, Habit.block_id == block.id, Habit.status == "active")
        .order_by(Habit.position, Habit.id)
        .all()
    )
    ids = [h.id for h in habits]
    if habit_id not in ids:
        raise HTTPException(404)
    idx = ids.index(habit_id)
    new_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= new_idx < len(habits):
        habits[idx], habits[new_idx] = habits[new_idx], habits[idx]
        for i, h in enumerate(habits):
            h.position = i
        db.commit()
    return RedirectResponse("/habits", status_code=303)
