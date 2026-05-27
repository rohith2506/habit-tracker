from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .config import settings
from .db import Base, engine
from . import models  # ensure models are imported so Base knows about them
from .templating import templates
from .routes import auth as auth_routes
from .routes import dashboard, checkin, habits, goals, feed, settings as settings_routes
from .scheduler import start_scheduler, stop_scheduler


STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist (dev convenience; Alembic owns prod migrations)
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": exc.status_code, "detail": exc.detail, "user": None},
        status_code=exc.status_code,
    )


app.include_router(auth_routes.router)
app.include_router(dashboard.router)
app.include_router(checkin.router)
app.include_router(habits.router)
app.include_router(goals.router)
app.include_router(feed.router)
app.include_router(settings_routes.router)
