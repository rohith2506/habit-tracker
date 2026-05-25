from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from ..auth import login_required, other_user
from ..blocks import block_progress, ensure_active_block, get_active_block
from ..db import get_db
from ..models import Block, BlockReview, Goal, Habit, User
from ..templating import templates


router = APIRouter()


def _can_open_mid(block: Block, today: date) -> bool:
    """Spec: active in week 4 ±3 days."""
    week4_start = block.start_date + timedelta(weeks=3)
    week4_end = block.start_date + timedelta(weeks=5) - timedelta(days=1)
    return week4_start - timedelta(days=3) <= today <= week4_end + timedelta(days=3)


def _can_open_end(block: Block, today: date) -> bool:
    """Spec: active in last week."""
    last_week_start = block.end_date - timedelta(days=6)
    return last_week_start <= today <= block.end_date + timedelta(days=14)  # also during grace post-end


def _my_reviews(db: OrmSession, block: Block, user: User) -> dict[str, BlockReview]:
    rows = (
        db.query(BlockReview)
        .filter(BlockReview.block_id == block.id, BlockReview.user_id == user.id)
        .all()
    )
    return {r.kind: r for r in rows}


@router.get("/block")
def page(
    request: Request,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    block = ensure_active_block(db)
    today = date.today()
    progress = block_progress(block, today)
    history = db.query(Block).filter(Block.status == "completed").order_by(Block.end_date.desc()).all()
    my_reviews = _my_reviews(db, block, user)
    other = other_user(db, user)
    other_reviews = _my_reviews(db, block, other) if other else {}
    return templates.TemplateResponse(
        "block.html",
        {
            "request": request,
            "user": user,
            "other": other,
            "block": block,
            "progress": progress,
            "can_open_mid": _can_open_mid(block, today),
            "can_open_end": _can_open_end(block, today),
            "my_reviews": my_reviews,
            "other_reviews": other_reviews,
            "history": history,
        },
    )


@router.get("/block/review/{kind}")
def review_form(
    kind: str,
    request: Request,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    if kind not in ("mid", "end"):
        raise HTTPException(404)
    block = ensure_active_block(db)
    today = date.today()
    if kind == "mid" and not _can_open_mid(block, today):
        raise HTTPException(403, "Mid-block review is only available around week 4")
    if kind == "end" and not _can_open_end(block, today):
        raise HTTPException(403, "End-of-block review is only available in the last week")

    my_goals = (
        db.query(Goal)
        .filter(Goal.user_id == user.id, Goal.block_id == block.id)
        .order_by(Goal.category, Goal.id)
        .all()
    )
    my_habits = (
        db.query(Habit)
        .filter(Habit.user_id == user.id, Habit.block_id == block.id, Habit.status == "active")
        .order_by(Habit.position, Habit.id)
        .all()
    )
    existing = _my_reviews(db, block, user).get(kind)
    return templates.TemplateResponse(
        f"block_review_{kind}.html",
        {
            "request": request,
            "user": user,
            "block": block,
            "goals": my_goals,
            "habits": my_habits,
            "existing": existing,
        },
    )


@router.post("/block/review/{kind}")
def review_submit(
    kind: str,
    note: str = Form(""),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    if kind not in ("mid", "end"):
        raise HTTPException(404)
    block = ensure_active_block(db)
    existing = (
        db.query(BlockReview)
        .filter(BlockReview.block_id == block.id, BlockReview.user_id == user.id, BlockReview.kind == kind)
        .one_or_none()
    )
    if existing:
        existing.note = note.strip() or None
    else:
        db.add(BlockReview(block_id=block.id, user_id=user.id, kind=kind, note=note.strip() or None))

    # If both users have completed this kind of review, set the block timestamp
    other = other_user(db, user)
    if other:
        other_review = (
            db.query(BlockReview)
            .filter(BlockReview.block_id == block.id, BlockReview.user_id == other.id, BlockReview.kind == kind)
            .one_or_none()
        )
        if other_review:
            if kind == "mid" and not block.mid_review_done_at:
                block.mid_review_done_at = datetime.utcnow()
            if kind == "end" and not block.end_review_done_at:
                block.end_review_done_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/block", status_code=303)


@router.post("/block/{block_id}/delete")
def delete_block(
    block_id: int,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    block = db.get(Block, block_id)
    if not block:
        raise HTTPException(404)
    db.delete(block)
    db.commit()
    return RedirectResponse("/block", status_code=303)


@router.post("/block/next")
def start_next(
    length_weeks: int = Form(8),
    carry_habits: str = Form("yes"),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    block = get_active_block(db)
    if not block:
        raise HTTPException(400, "No active block")
    if not block.end_review_done_at and date.today() < block.end_date:
        raise HTTPException(400, "Finish the end-of-block review first or wait for the block to end")
    # Close current
    block.status = "completed"
    db.flush()
    # Open new
    length_weeks = 8 if length_weeks not in (4, 6, 8, 12) else length_weeks
    today = date.today()
    new_block = Block(
        start_date=today,
        end_date=today + timedelta(weeks=length_weeks) - timedelta(days=1),
        length_weeks=length_weeks,
        status="active",
    )
    db.add(new_block)
    db.flush()

    # Carry habits if requested
    if carry_habits == "yes":
        for u in db.query(User).all():
            old_habits = (
                db.query(Habit)
                .filter(Habit.user_id == u.id, Habit.block_id == block.id, Habit.status == "active")
                .order_by(Habit.position, Habit.id)
                .all()
            )
            for h in old_habits:
                db.add(Habit(
                    user_id=u.id, block_id=new_block.id,
                    name=h.name, icon=h.icon,
                    frequency=h.frequency, weekly_target=h.weekly_target,
                    position=h.position, status="active",
                ))
    db.commit()
    return RedirectResponse("/block", status_code=303)
