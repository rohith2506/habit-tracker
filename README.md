# Together

Two-person accountability tracker. See `DESIGN.md` for the full spec.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Seed two users + an initial 8-week block
python seed.py

# Run the dev server
uvicorn app.main:app --reload
```

Then open <http://localhost:8000>. Sign in as:

- `you` / `together-you`
- `her` / `together-her`

Change the passwords from `/settings` after first login.

## Deploy

```bash
fly launch          # follow prompts; mount a volume at /data
fly secrets set SECRET_KEY="$(openssl rand -hex 32)"
fly deploy
fly ssh console -C "python seed.py"   # seed users once
```

Backups: add Litestream as a sidecar in the Dockerfile when you're ready.

## Layout

```
app/
  main.py              # FastAPI app + lifespan
  config.py            # Settings (env-driven)
  db.py                # SQLAlchemy engine + session
  models.py            # All ORM models
  security.py          # bcrypt + session id
  auth.py              # session deps (login_required)
  time_utils.py        # per-user timezone helpers
  blocks.py            # active block + progress
  stats.py             # streak, weekly %, goal pace
  scheduler.py         # APScheduler day-rollover job
  templating.py        # Jinja env + filters
  routes/              # one file per area
  templates/           # Jinja templates (+ partials/)
  static/              # CSS
alembic/               # migrations
seed.py                # create the two users + initial block
Dockerfile, fly.toml
```
