from datetime import datetime, timedelta
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from .config import settings
from .db import get_db
from .models import Session, User
from .security import new_session_id


def create_session(db: OrmSession, user: User) -> Session:
    sid = new_session_id()
    sess = Session(
        id=sid,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=settings.session_days),
    )
    db.add(sess)
    db.commit()
    return sess


def destroy_session(db: OrmSession, session_id: str) -> None:
    sess = db.get(Session, session_id)
    if sess:
        db.delete(sess)
        db.commit()


def _resolve_user(db: OrmSession, session_id: Optional[str]) -> Optional[User]:
    if not session_id:
        return None
    sess = db.get(Session, session_id)
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        db.delete(sess)
        db.commit()
        return None
    return db.get(User, sess.user_id)


def current_user_optional(
    request: Request,
    db: OrmSession = Depends(get_db),
) -> Optional[User]:
    sid = request.cookies.get(settings.session_cookie_name)
    return _resolve_user(db, sid)


def login_required(
    request: Request,
    db: OrmSession = Depends(get_db),
) -> User:
    sid = request.cookies.get(settings.session_cookie_name)
    user = _resolve_user(db, sid)
    if not user:
        # For HTMX requests, return 401; otherwise redirect to /login
        if request.headers.get("HX-Request"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Login required",
            headers={"Location": "/login"},
        )
    return user


def other_user(db: OrmSession, me: User) -> Optional[User]:
    return db.query(User).filter(User.id != me.id).first()
