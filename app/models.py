from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Date, Text, ForeignKey,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16))  # "blue" or "pink"
    avatar_initial: Mapped[str] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    habits: Mapped[List["Habit"]] = relationship(back_populates="user")
    goals: Mapped[List["Goal"]] = relationship(back_populates="user")
    checkins: Mapped[List["CheckIn"]] = relationship(back_populates="user")
    posts: Mapped[List["CreativePost"]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    length_weeks: Mapped[int] = mapped_column(Integer, default=8)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed
    mid_review_done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_review_done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32))  # body | skill | creative | learning
    kind: Mapped[str] = mapped_column(String(16))  # measurable | binary
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | hit | partially_hit | missed | abandoned | amended

    # measurable
    start_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # binary
    latest_result: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amendment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="goals")
    progress: Mapped[List["GoalProgress"]] = relationship(back_populates="goal", cascade="all, delete-orphan")
    attempts: Mapped[List["GoalAttempt"]] = relationship(back_populates="goal", cascade="all, delete-orphan")
    milestones: Mapped[List["GoalMilestone"]] = relationship(back_populates="goal", cascade="all, delete-orphan", order_by="GoalMilestone.position")

    __table_args__ = (
        Index("ix_goals_block_user", "block_id", "user_id"),
    )


class GoalProgress(Base):
    __tablename__ = "goal_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Float)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    goal: Mapped["Goal"] = relationship(back_populates="progress")


class GoalAttempt(Base):
    __tablename__ = "goal_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    result: Mapped[bool] = mapped_column(Boolean)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    goal: Mapped["Goal"] = relationship(back_populates="attempts")


class GoalMilestone(Base):
    __tablename__ = "goal_milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(120))
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    goal: Mapped["Goal"] = relationship(back_populates="milestones")


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(64), default="ti-check")
    frequency: Mapped[str] = mapped_column(String(16), default="daily")  # daily | weekly
    weekly_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1..6 when weekly
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | paused | ended
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pause_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="habits")

    __table_args__ = (
        Index("ix_habits_block_user_status", "block_id", "user_id", "status"),
    )


class CheckIn(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="checkins")
    entries: Mapped[List["CheckInEntry"]] = relationship(back_populates="checkin", cascade="all, delete-orphan")
    adhoc_items: Mapped[List["AdHocItem"]] = relationship(back_populates="checkin", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_checkin_user_date"),
    )


class CheckInEntry(Base):
    __tablename__ = "checkin_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_in_id: Mapped[int] = mapped_column(ForeignKey("checkins.id", ondelete="CASCADE"))
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(12), default="pending")  # done | rest | missed | pending

    checkin: Mapped["CheckIn"] = relationship(back_populates="entries")
    habit: Mapped["Habit"] = relationship()

    __table_args__ = (
        UniqueConstraint("check_in_id", "habit_id", name="uq_entry_checkin_habit"),
    )


class AdHocItem(Base):
    __tablename__ = "adhoc_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_in_id: Mapped[int] = mapped_column(ForeignKey("checkins.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    checkin: Mapped["CheckIn"] = relationship(back_populates="adhoc_items")


class CreativePost(Base):
    __tablename__ = "creative_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))  # writing | piano | painting | reading | puzzle
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="posts")
    reactions: Mapped[List["Reaction"]] = relationship(back_populates="post", cascade="all, delete-orphan")


class Reaction(Base):
    __tablename__ = "reactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("creative_posts.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    emoji: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    post: Mapped["CreativePost"] = relationship(back_populates="reactions")


class BlockReview(Base):
    __tablename__ = "block_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))  # "mid" | "end"
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("block_id", "user_id", "kind", name="uq_block_review"),
    )
