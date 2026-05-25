from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from ..auth import login_required
from ..db import get_db
from ..models import User
from ..security import hash_password, verify_password
from ..templating import templates


router = APIRouter()


COMMON_TZ = sorted([
    "UTC", "Europe/Amsterdam", "Europe/London", "Europe/Berlin", "Europe/Paris", "Europe/Madrid",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Toronto",
    "Asia/Kolkata", "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore", "Asia/Dubai",
    "Australia/Sydney", "Pacific/Auckland",
])


@router.get("/settings")
def page(request: Request, user: User = Depends(login_required)):
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "user": user, "tz_options": COMMON_TZ, "saved": False},
    )


@router.post("/settings")
def update(
    request: Request,
    display_name: str = Form(...),
    avatar_initial: str = Form(...),
    timezone: str = Form(...),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    name = display_name.strip()
    initial = (avatar_initial.strip()[:2] or user.avatar_initial).upper()
    if name:
        user.display_name = name
    user.avatar_initial = initial
    if timezone in available_timezones():
        user.timezone = timezone
    db.commit()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "user": user, "tz_options": COMMON_TZ, "saved": True},
    )


@router.post("/settings/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "user": user, "tz_options": COMMON_TZ, "pw_error": "Current password is wrong."},
            status_code=400,
        )
    if len(new_password) < 6:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "user": user, "tz_options": COMMON_TZ, "pw_error": "New password too short."},
            status_code=400,
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request, "user": user, "tz_options": COMMON_TZ, "pw_error": "Passwords don't match."},
            status_code=400,
        )
    user.password_hash = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "user": user, "tz_options": COMMON_TZ, "pw_saved": True},
    )
