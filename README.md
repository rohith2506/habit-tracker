# Together

Two-person accountability tracker. See [`DESIGN.md`](DESIGN.md) for the full spec.

**Live:** <https://hachimi.fly.dev>

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Seed the two users + an initial 8-week block (defaults in seed.py)
python seed.py

# Run the dev server (auto-reloads on file changes)
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. Default seeded usernames are `rohith` and `akshaya` — login is case-insensitive, so `Rohith` works too. Both share the same default password defined in `seed.py`; change them via `/settings` after first login.

To wipe the local DB and start over:

```bash
python seed.py --reset
```

## Deploy (Fly.io)

The app is deployed to Fly as `hachimi`, region `ams`, with a 1 GB volume mounted at `/data`.

```bash
# Deploy a new revision
fly deploy -a hachimi

# Tail logs
fly logs -a hachimi

# SSH into the running machine
fly ssh console -a hachimi

# Re-seed users on prod (overwrites if --reset)
fly ssh console -a hachimi -C "python seed.py"

# Rotate session secret
fly secrets set SECRET_KEY="$(openssl rand -hex 32)" -a hachimi
```

The SQLite database lives at `/data/db.sqlite` on the Fly volume; uploads at `/data/uploads/`. Volume snapshots (5-day retention) cover backups for now — Litestream isn't wired in yet.

## Layout

```
app/
  main.py              # FastAPI app + lifespan
  config.py            # Settings (env-driven via pydantic-settings)
  db.py                # SQLAlchemy engine + session
  models.py            # All ORM models
  security.py          # bcrypt + session id
  auth.py              # Session deps (login_required, current_user_optional)
  time_utils.py        # Per-user timezone helpers
  blocks.py            # Active block + progress
  stats.py             # Streak, weekly %, goal pace, day rollover
  scheduler.py         # APScheduler day-rollover job
  templating.py        # Jinja env + filters
  routes/              # One file per area
    auth.py            # /login, /logout
    dashboard.py       # /
    checkin.py         # /checkin + entry cycling + ad-hoc items
    habits.py          # /habits CRUD (incl. delete)
    goals.py           # /goals CRUD (incl. delete)
    feed.py            # /feed + composer + uploads + reactions/comments (incl. delete)
    block.py           # /block + mid/end reviews + next-block + delete
    settings.py        # /settings + password change
  templates/           # Jinja templates
    partials/          # Reusable fragments (habit_row, checkin_row, goal_card, post_card, …)
  static/app.css       # Tailwind-layered custom styles
alembic/               # DB migrations (initial migration in versions/)
seed.py                # Create the two users + initial block (--reset wipes)
Dockerfile, fly.toml   # Production deploy config
```

## Behavior notes

- Each user has their own timezone; "today" is computed per user.
- Daily rollover is handled by an APScheduler hourly job that locks past-day check-ins after a 6-hour grace window.
- Habits, goals, posts, and entire blocks all have **delete** (owner-only). Habits also support a non-destructive `End` that preserves history.
- Cascade is at the DB level via `ondelete="CASCADE"` + `PRAGMA foreign_keys=ON`.
- File uploads are served only through `/uploads/:filename`, which requires a valid session — never as static files.
