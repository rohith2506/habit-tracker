from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from ..auth import login_required, other_user
from ..db import get_db
from ..models import Goal, GoalAttempt, GoalMilestone, GoalProgress, User
from ..stats import goal_progress_summary
from ..templating import templates


router = APIRouter()


CATEGORIES = ["body", "skill", "creative", "learning"]


def _opt_float(s: str | None) -> float | None:
    if s is None or s.strip() == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _goals_for(db: OrmSession, user_id: int) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id)
        .order_by(Goal.category, Goal.id)
        .all()
    )


def _annotate(goals: list[Goal]):
    return [{"goal": g, "summary": goal_progress_summary(g)} for g in goals]


@router.get("/goals")
def page(
    request: Request,
    view: str = "me",
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    if view not in ("me", "other", "both"):
        view = "me"
    other = other_user(db, user)

    my_goals = _annotate(_goals_for(db, user.id))
    other_goals = _annotate(_goals_for(db, other.id)) if other else []

    return templates.TemplateResponse(
        "goals.html",
        {
            "request": request,
            "user": user,
            "other": other,
            "view": view,
            "categories": CATEGORIES,
            "my_goals": my_goals,
            "other_goals": other_goals,
        },
    )


@router.post("/goals")
def create(
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("body"),
    kind: str = Form("measurable"),
    start_value: str | None = Form(None),
    target_value: str | None = Form(None),
    unit: str = Form(""),
    milestones: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    sv = _opt_float(start_value)
    tv = _opt_float(target_value)
    title = title.strip()
    if not title:
        raise HTTPException(400, "Title required")
    if category not in CATEGORIES:
        category = "body"
    if kind not in ("measurable", "binary"):
        kind = "measurable"

    g = Goal(
        user_id=user.id,
        title=title, description=description.strip() or None,
        category=category, kind=kind, status="active",
    )
    if kind == "measurable":
        g.start_value = sv if sv is not None else 0.0
        g.target_value = tv if tv is not None else 0.0
        g.unit = unit.strip() or None
    db.add(g)
    db.flush()

    # Milestones — comma-separated labels, optionally "Label:value"
    raw = [m.strip() for m in milestones.split(",") if m.strip()]
    for i, raw_m in enumerate(raw):
        label, value = raw_m, None
        if ":" in raw_m:
            label, _, val_str = raw_m.partition(":")
            try:
                value = float(val_str)
            except ValueError:
                value = None
        db.add(GoalMilestone(goal_id=g.id, position=i, label=label.strip(), value=value))

    db.commit()
    return RedirectResponse("/goals", status_code=303)


@router.post("/goals/{goal_id}/update")
def amend(
    goal_id: int,
    title: str = Form(None),
    description: str = Form(None),
    target_value: str | None = Form(None),
    reason: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404)
    changed = False
    if title is not None and title.strip():
        g.title = title.strip()
        changed = True
    if description is not None:
        g.description = description.strip() or None
        changed = True
    tv = _opt_float(target_value)
    if tv is not None and g.kind == "measurable":
        g.target_value = tv
        changed = True
    if changed:
        g.amended_at = datetime.utcnow()
        g.amendment_reason = reason.strip() or None
    db.commit()
    return RedirectResponse("/goals", status_code=303)


def _auto_hit_milestones(db: OrmSession, goal: Goal, current: float):
    for m in goal.milestones:
        if m.value is None or m.hit_at is not None:
            continue
        # Direction-agnostic: if target > start, hitting means current >= m.value; if target < start (e.g. weight loss), current <= m.value.
        if goal.target_value is not None and goal.start_value is not None:
            if goal.target_value >= goal.start_value:
                if current >= m.value:
                    m.hit_at = datetime.utcnow()
            else:
                if current <= m.value:
                    m.hit_at = datetime.utcnow()


@router.post("/goals/{goal_id}/progress")
def log_progress(
    goal_id: int,
    value: str = Form(...),
    note: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404)
    if g.kind != "measurable":
        raise HTTPException(400, "Not a measurable goal")
    v = _opt_float(value)
    if v is None:
        raise HTTPException(400, "Value must be a number")
    p = GoalProgress(goal_id=g.id, value=v, note=note.strip() or None)
    db.add(p)
    _auto_hit_milestones(db, g, v)
    db.commit()
    return RedirectResponse("/goals", status_code=303)


@router.post("/goals/{goal_id}/attempt")
def log_attempt(
    goal_id: int,
    result: str = Form("pass"),
    note: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404)
    if g.kind != "binary":
        raise HTTPException(400, "Not a binary goal")
    res = result == "pass"
    a = GoalAttempt(goal_id=g.id, result=res, note=note.strip() or None)
    db.add(a)
    g.latest_result = res
    g.last_attempt_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/goals", status_code=303)


@router.post("/goals/{goal_id}/milestone/{m_id}/toggle")
def toggle_milestone(
    goal_id: int,
    m_id: int,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404)
    m = db.get(GoalMilestone, m_id)
    if not m or m.goal_id != g.id:
        raise HTTPException(404)
    m.hit_at = None if m.hit_at else datetime.utcnow()
    db.commit()
    return RedirectResponse("/goals", status_code=303)


@router.post("/goals/{goal_id}/delete")
def delete(
    goal_id: int,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404)
    db.delete(g)
    db.commit()
    return RedirectResponse("/goals", status_code=303)


@router.post("/goals/{goal_id}/resolve")
def resolve(
    goal_id: int,
    status: str = Form("hit"),
    resolution_note: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404)
    if status not in ("hit", "partially_hit", "missed", "abandoned"):
        status = "hit"
    g.status = status
    g.resolution_note = resolution_note.strip() or None
    db.commit()
    return RedirectResponse("/goals", status_code=303)
