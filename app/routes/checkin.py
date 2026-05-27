from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session as OrmSession

from ..auth import login_required
from ..db import get_db
from ..models import AdHocItem, CheckIn, CheckInEntry, Habit, User
from ..stats import (
    cycle_state, ensure_entries_for, get_or_create_today, weekly_count_for,
)
from ..templating import templates
from ..time_utils import today_for, is_within_grace


router = APIRouter()


def _active_habits(db: OrmSession, user: User) -> list[Habit]:
    return (
        db.query(Habit)
        .filter(Habit.user_id == user.id, Habit.status == "active")
        .order_by(Habit.position, Habit.id)
        .all()
    )


def _row_context(db: OrmSession, user: User, entry: CheckInEntry, habit: Habit) -> dict:
    weekly_done = weekly_count_for(db, user, habit, today_for(user)) if habit.frequency == "weekly" else None
    return {
        "entry": entry,
        "habit": habit,
        "weekly_done": weekly_done,
    }


@router.get("/checkin")
def page(request: Request, user: User = Depends(login_required), db: OrmSession = Depends(get_db)):
    ci = get_or_create_today(db, user)
    habits = _active_habits(db, user)
    ensure_entries_for(db, ci, habits)
    # map entries by habit id
    entries_by_habit = {e.habit_id: e for e in ci.entries}
    rows = []
    today = today_for(user)
    for h in habits:
        e = entries_by_habit.get(h.id)
        if not e:
            continue
        weekly_done = weekly_count_for(db, user, h, today) if h.frequency == "weekly" else None
        rows.append({"habit": h, "entry": e, "weekly_done": weekly_done})
    return templates.TemplateResponse(
        "checkin.html",
        {
            "request": request,
            "user": user,
            "checkin": ci,
            "rows": rows,
            "today": today,
            "locked": ci.locked or not is_within_grace(ci.date, user),
        },
    )


@router.post("/checkin/entry/{habit_id}/cycle")
def cycle(
    habit_id: int,
    request: Request,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    ci = get_or_create_today(db, user)
    if ci.locked:
        raise HTTPException(409, "Check-in is locked")
    entry = (
        db.query(CheckInEntry)
        .filter(CheckInEntry.check_in_id == ci.id, CheckInEntry.habit_id == habit_id)
        .one_or_none()
    )
    if not entry:
        # Create on the fly if habit became active mid-day
        habit = db.get(Habit, habit_id)
        if not habit or habit.user_id != user.id:
            raise HTTPException(404)
        entry = CheckInEntry(check_in_id=ci.id, habit_id=habit_id, state="pending")
        db.add(entry)
        db.commit()
        db.refresh(entry)
    entry.state = cycle_state(entry.state)
    db.commit()
    habit = db.get(Habit, habit_id)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "partials/checkin_row.html",
            {"request": request, "user": user, **_row_context(db, user, entry, habit)},
        )
    return RedirectResponse("/checkin", status_code=303)


@router.post("/checkin/note")
def save_note(
    note: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    ci = get_or_create_today(db, user)
    if ci.locked:
        raise HTTPException(409, "Check-in is locked")
    ci.note = note.strip() or None
    db.commit()
    return Response(status_code=204)


@router.post("/checkin/adhoc")
def add_adhoc(
    request: Request,
    text: str = Form(...),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    ci = get_or_create_today(db, user)
    if ci.locked:
        raise HTTPException(409, "Check-in is locked")
    text = text.strip()
    if not text:
        raise HTTPException(400)
    item = AdHocItem(check_in_id=ci.id, text=text, done=False)
    db.add(item)
    db.commit()
    db.refresh(item)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/adhoc_item.html", {"request": request, "item": item})
    return RedirectResponse("/checkin", status_code=303)


@router.post("/checkin/adhoc/{item_id}/toggle")
def toggle_adhoc(
    item_id: int,
    request: Request,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    item = db.get(AdHocItem, item_id)
    if not item:
        raise HTTPException(404)
    ci = db.get(CheckIn, item.check_in_id)
    if not ci or ci.user_id != user.id:
        raise HTTPException(404)
    if ci.locked:
        raise HTTPException(409, "Locked")
    item.done = not item.done
    db.commit()
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/adhoc_item.html", {"request": request, "item": item})
    return RedirectResponse("/checkin", status_code=303)


@router.post("/checkin/adhoc/{item_id}/delete")
def delete_adhoc(
    item_id: int,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    item = db.get(AdHocItem, item_id)
    if not item:
        return Response(status_code=204)
    ci = db.get(CheckIn, item.check_in_id)
    if not ci or ci.user_id != user.id:
        raise HTTPException(404)
    if ci.locked:
        raise HTTPException(409, "Locked")
    db.delete(item)
    db.commit()
    return Response(status_code=200, content="")


@router.post("/checkin/save")
def save(
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    ci = get_or_create_today(db, user)
    ci.submitted_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/checkin", status_code=303)
