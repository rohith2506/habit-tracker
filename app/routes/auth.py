from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from ..config import settings
from ..db import get_db
from ..models import User
from ..security import verify_password
from ..auth import create_session, destroy_session, current_user_optional
from ..templating import templates


router = APIRouter()


@router.get("/login")
def login_form(request: Request, user: User | None = Depends(current_user_optional)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "user": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: OrmSession = Depends(get_db),
):
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "user": None, "error": "Incorrect username or password."},
            status_code=400,
        )
    sess = create_session(db, user)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        settings.session_cookie_name,
        sess.id,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        path="/",
    )
    return resp


@router.post("/logout")
def logout(request: Request, db: OrmSession = Depends(get_db)):
    sid = request.cookies.get(settings.session_cookie_name)
    if sid:
        destroy_session(db, sid)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(settings.session_cookie_name, path="/")
    return resp
