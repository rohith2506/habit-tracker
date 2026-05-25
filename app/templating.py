from pathlib import Path
from datetime import datetime, date

import markdown as md
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .time_utils import utc_to_local


TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def fmt_date(d, fmt="%a %b %-d"):
    if d is None:
        return ""
    return d.strftime(fmt)


def fmt_datetime(dt, fmt="%b %-d, %H:%M"):
    if dt is None:
        return ""
    return dt.strftime(fmt)


def fmt_local(dt, user, fmt="%b %-d, %H:%M"):
    if dt is None or user is None:
        return ""
    return utc_to_local(dt, user).strftime(fmt)


def render_markdown(text: str) -> Markup:
    if not text:
        return Markup("")
    html = md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return Markup(html)


def pct(value, max_value, fallback="0"):
    try:
        if not max_value:
            return fallback
        return f"{round(100.0 * value / max_value)}"
    except Exception:
        return fallback


templates.env.filters["fmt_date"] = fmt_date
templates.env.filters["fmt_datetime"] = fmt_datetime
templates.env.filters["fmt_local"] = fmt_local
templates.env.filters["markdown"] = render_markdown
templates.env.filters["pct"] = pct
templates.env.globals["now"] = datetime.utcnow
templates.env.globals["today"] = date.today
