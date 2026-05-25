import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session as OrmSession

from ..auth import login_required, other_user
from ..config import UPLOADS_PATH
from ..db import get_db
from ..models import CreativePost, Reaction, User
from ..templating import templates


router = APIRouter()


POST_TYPES = ["writing", "piano", "painting", "reading", "puzzle"]
EMOJI_WHITELIST = ["❤️", "🔥", "✨", "🎉", "👏", "😍"]

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg"}


def _icon_for(kind: str) -> str:
    return {
        "writing": "ti-pencil",
        "piano": "ti-piano",
        "painting": "ti-palette",
        "reading": "ti-book",
        "puzzle": "ti-puzzle",
    }.get(kind, "ti-sparkles")


@router.get("/feed")
def page(
    request: Request,
    filter: str = "all",
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    q = db.query(CreativePost).order_by(CreativePost.created_at.desc())
    if filter in POST_TYPES:
        q = q.filter(CreativePost.type == filter)
    posts = q.limit(100).all()
    return templates.TemplateResponse(
        "feed.html",
        {
            "request": request,
            "user": user,
            "posts": posts,
            "filter": filter,
            "types": POST_TYPES,
            "icon_for": _icon_for,
            "emoji_whitelist": EMOJI_WHITELIST,
        },
    )


@router.get("/feed/new")
def composer(request: Request, user: User = Depends(login_required)):
    return templates.TemplateResponse(
        "feed_new.html",
        {"request": request, "user": user, "types": POST_TYPES},
    )


@router.post("/feed")
async def create(
    type: str = Form(...),
    body: str = Form(""),
    media: UploadFile = File(None),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    if type not in POST_TYPES:
        raise HTTPException(400, "Unknown post type")

    media_url = None
    if media is not None and media.filename:
        ext = Path(media.filename).suffix.lower()
        if type == "painting" and ext not in IMAGE_EXT:
            raise HTTPException(400, "Painting needs an image (png/jpg/webp/gif)")
        if type == "piano" and ext not in AUDIO_EXT:
            raise HTTPException(400, "Piano needs an audio file (mp3/m4a/wav/ogg)")
        if type not in ("painting", "piano"):
            raise HTTPException(400, "This post type doesn't take an upload")
        fname = f"{secrets.token_hex(12)}{ext}"
        dest = UPLOADS_PATH / fname
        with open(dest, "wb") as f:
            while True:
                chunk = await media.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        media_url = fname

    body = (body or "").strip()
    if type in ("writing", "reading", "puzzle") and not body:
        raise HTTPException(400, "Body required for this post type")
    if type in ("painting", "piano") and not media_url:
        raise HTTPException(400, "Upload required for this post type")

    post = CreativePost(user_id=user.id, type=type, body=body or None, media_url=media_url)
    db.add(post)
    db.commit()
    return RedirectResponse("/feed", status_code=303)


@router.post("/feed/{post_id}/react")
def react(
    post_id: int,
    emoji: str = Form(...),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    post = db.get(CreativePost, post_id)
    if not post:
        raise HTTPException(404)
    if emoji not in EMOJI_WHITELIST:
        raise HTTPException(400, "Unknown emoji")
    existing = (
        db.query(Reaction)
        .filter(Reaction.post_id == post.id, Reaction.user_id == user.id, Reaction.comment.is_(None))
        .first()
    )
    if existing:
        if existing.emoji == emoji:
            db.delete(existing)
        else:
            existing.emoji = emoji
    else:
        db.add(Reaction(post_id=post.id, user_id=user.id, emoji=emoji))
    db.commit()
    return RedirectResponse("/feed", status_code=303)


@router.post("/feed/{post_id}/comment")
def comment(
    post_id: int,
    text: str = Form(...),
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    post = db.get(CreativePost, post_id)
    if not post:
        raise HTTPException(404)
    text = text.strip()
    if not text:
        raise HTTPException(400)
    db.add(Reaction(post_id=post.id, user_id=user.id, comment=text))
    db.commit()
    return RedirectResponse("/feed", status_code=303)


@router.post("/feed/{post_id}/delete")
def delete_post(
    post_id: int,
    user: User = Depends(login_required),
    db: OrmSession = Depends(get_db),
):
    post = db.get(CreativePost, post_id)
    if not post:
        raise HTTPException(404)
    if post.user_id != user.id:
        raise HTTPException(403, "You can only delete your own posts")
    if post.media_url:
        target = UPLOADS_PATH / Path(post.media_url).name
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
    db.delete(post)
    db.commit()
    return RedirectResponse("/feed", status_code=303)


@router.get("/uploads/{filename}")
def serve_upload(filename: str, user: User = Depends(login_required)):
    # Basic safety: no path traversal
    safe = Path(filename).name
    target = UPLOADS_PATH / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(404)
    return FileResponse(str(target))
