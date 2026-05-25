from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .models import Block


def get_active_block(db: OrmSession) -> Optional[Block]:
    return db.execute(select(Block).where(Block.status == "active")).scalar_one_or_none()


def ensure_active_block(db: OrmSession, length_weeks: int = 8) -> Block:
    block = get_active_block(db)
    if block:
        return block
    today = date.today()
    block = Block(
        start_date=today,
        end_date=today + timedelta(weeks=length_weeks) - timedelta(days=1),
        length_weeks=length_weeks,
        status="active",
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def block_progress(block: Block, today: Optional[date] = None) -> dict:
    today = today or date.today()
    total_days = (block.end_date - block.start_date).days + 1
    days_elapsed = max(0, min(total_days, (today - block.start_date).days + 1))
    days_remaining = max(0, (block.end_date - today).days)
    week_n = min(block.length_weeks, max(1, (days_elapsed + 6) // 7))
    elapsed_fraction = days_elapsed / total_days if total_days else 0.0
    return {
        "total_days": total_days,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "week_n": week_n,
        "length_weeks": block.length_weeks,
        "elapsed_fraction": elapsed_fraction,
    }
