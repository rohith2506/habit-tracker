# Together — design spec

A two-person accountability tracker for a long-distance couple. Not a habit-tracker template — a custom tool for two specific people to motivate each other on body composition, skill milestones, and creative practice.

This document is the v1 spec. Build to this. Where it's silent, prefer simplicity.

> **Post-v1 change (2026-05-27): Blocks removed.** The 8-week **Block** container and its mid/end **reviews**, next-block setup, carry-over, and history have been removed to cut complexity. Goals and habits are now **global per user** (no `block_id`, no block dates). Goal **pace** ("on track / behind pace") depended on the block timeframe and was removed too — goals keep progress %, milestones, attempts, status, amend, and resolve. The sections below describing Block, BlockReview, `/block*`, and pace are retained for historical context but no longer reflect the implementation.

---

## Users

Exactly two. Pre-seeded — no signup flow, no invites. The two accounts exist from day one.

- User A — "you" (in the mockups, blue)
- User B — "her" (in the mockups, pink)

Each user picks their own display name and avatar initial. Color assignment is fixed at seed time.

---

## Stack

- **Backend:** FastAPI (Python 3.12+), SQLAlchemy 2.0, Alembic for migrations
- **Frontend:** Jinja2 server-rendered templates + HTMX for interactivity + vanilla JS where HTMX isn't enough + Tailwind for styling
- **Database:** SQLite, file lives on the same Fly Volume as the app
- **Auth:** Username + password, session cookies (signed, httpOnly, secure in prod). No email, no magic links, no OAuth. Two users, both know the passwords.
- **File uploads:** Stored on the same Fly Volume under `/data/uploads/`. Served by FastAPI through an authenticated route — not directly exposed.
- **Deploy:** Single Docker container on Fly.io. One Fly app, one machine, one volume mounted at `/data`. Litestream for continuous SQLite backup to S3-compatible object storage (Cloudflare R2 recommended, but optional for v1).

No frontend build step. HTMX and Alpine (optional) loaded from CDN. Tailwind via CDN for v1 — switch to a build step only if it becomes a real problem.

---

## Core concepts

### Block

The 8-week container both users operate in. **Shared** — there's one active block at a time, both users live inside it.

- `start_date`, `end_date`
- `length_weeks` (default 8, configurable 4 / 6 / 8 / 12 at creation)
- `status` — active, completed
- `mid_review_done_at`, `end_review_done_at` — timestamps when reviews are submitted
- Only one block can be `active` at a time
- New block starts when the previous one's end review is submitted (or manually started)

### Goal

An outcome a single user commits to for the duration of a block. **Individual** — each user has their own goals.

- `user_id`, `block_id`
- `title` — short, e.g. "Lose 2 kg" / "Tuck front lever 10s hold"
- `description` — optional longer context
- `category` — body / skill / creative / learning (drives icon + grouping)
- `kind` — `measurable` or `binary`
  - **measurable:** has `start_value`, `target_value`, `unit` (kg, seconds, words, pages, etc.), and a stream of `GoalProgress` entries
  - **binary:** done / not done, with optional `attempt_logs` (each attempt = a row, latest result wins)
- `milestones` — optional ordered list of sub-targets within a measurable goal (e.g. front lever progression chips: 3s, 4s, 5s, 6s, 10s)
- `status` — active, hit, partially_hit, missed, abandoned, amended
- `resolution_note` — short reflection added at end-of-block

Behavior:
- Goals are created at block start (or any time, but the ritual is at block start)
- Progress is logged manually — measurable goals via "Log progress" (creates a `GoalProgress` row); binary via "Log attempt"
- Goals cannot be deleted mid-block; they can be **amended** (with reason) which keeps history. At mid-block review users can adjust targets.
- Pace calculation: for measurable goals, given current progress and time elapsed, compute "at current pace, will finish in week X." Show as a small note, **not** as a shaming badge. ("On track" / "behind pace" badges are fine, but the language is honest, not punitive.)

### Habit

Something tracked daily in the check-in. **Individual** — each user has their own habit list.

- `user_id`, `block_id`
- `name`, `icon`
- `frequency` — `daily` or `weekly_n` where `n` is 1–6
- `position` — for manual ordering
- `status` — active, paused, ended
- `created_at`, `paused_at`, `ended_at`, `pause_reason`

Behavior:
- Habits live within a block. When a new block starts, last block's habits are carried over by default (user can edit).
- Can be added mid-block freely.
- Cannot be hard-deleted — `end` marks them ended and they stop appearing in new daily check-ins. Historical check-ins still reference them.
- Editing name/icon is free. Changing frequency is also free but only affects future calculation, not past.
- Soft cap: warn at 8 habits ("keep the list small"), don't block.

### CheckIn

One per user per day. Tracks completion state of that user's habits.

- `user_id`, `date` (the user's *local* date — see Timezones below)
- `note` — optional free text for the day
- `submitted_at` — when the user tapped "Save check-in"
- Has many `CheckInEntry` rows (one per habit) and many `AdHocItem` rows (one-off items for that day only)

### CheckInEntry

- `check_in_id`, `habit_id`
- `state` — `done` / `rest` / `missed` / `pending`
  - `done` — user completed it
  - `rest` — intentional rest (doesn't count as missed for streak / consistency)
  - `missed` — explicitly marked as missed (rare; mostly inferred at end of day)
  - `pending` — default until day rolls over; at midnight in user's TZ, unmarked entries become `missed` (or stay pending if not yet end of day for that user)

### AdHocItem

- `check_in_id`
- `text`
- `done` (bool)

Doesn't affect any consistency stats. Pure "todo for today."

### CreativePost

The shared feed. Both users can post; both can see all posts; reactions allowed.

- `user_id`
- `type` — writing / piano / painting / reading / puzzle
- `body` — markdown text (for writing posts, reading reflections)
- `media_url` — path to an image (paintings) or audio (piano clips) on the volume, served via authenticated route
- `created_at`
- Has many `Reaction` rows

### Reaction

- `post_id`, `user_id`
- `emoji` — single character (heart, fire, sparkle, etc. — short whitelist)
- `comment` — optional text reply
- One reaction-emoji per user per post (changing emoji replaces it); comments can be multiple

---

## Screens

All paths are GET unless noted. All POST/PATCH/DELETE routes return either a redirect (full-page) or an HTMX fragment (partial), depending on the `HX-Request` header.

### `/login`
Username + password form. POST sets a session cookie, redirects to `/`.

### `/` — Dashboard (side-by-side)
The main view. Both users' columns shown together.

For each user column:
- Avatar + name + "today: X of Y done"
- **Today's check-in** — habit list with current state for today (read-only on dashboard; tap takes you to `/checkin`)
- **Goals** — compact list with progress bars
- **Streak + weekly %** — small footer row, subtle, not gamified

Below: **Creative feed** — combined feed, chronological, both users' posts mixed.

### `/checkin` — Today's check-in (own view)
- Date header in the user's timezone
- List of own active habits
  - Each is a row with icon, name, frequency hint ("3 of 5 this week" for weekly habits)
  - Tap cycles state: pending → done → rest → pending
  - On weekly habits, the count updates live as state changes
- **Just for today** section — list of ad-hoc items + add row
- Optional note textarea
- Save button (sticky bottom on mobile)

Day rollover: at the user's local midnight, today's pending entries either persist as `missed` (if it's now "yesterday") or stay editable for a grace window of, say, 6 hours into the next day (configurable constant). After grace window, that day is locked.

### `/goals` — Goals
Tab strip: **You** / **Her** / **Both**

Default is "You." Each tab shows the relevant goals grouped by category, with progress bars, status badges, last-logged info, and action buttons (log progress / log attempt / amend).

"Both" view is a denser combined layout for the Sunday review.

### `/habits` — Habits setup (own view)
- Active habits list with drag-to-reorder, inline frequency toggle, "..." menu (rename, change icon, pause, end)
- Add-a-habit row at the bottom
- "Paused or ended" section below

### `/feed` — Creative feed (full view)
Same content as the dashboard's bottom strip, but full-page, more vertical room. Filters: all / writing / piano / painting / reading / puzzle. Post button (top-right) opens a composer.

### `/feed/new` — Composer
- Pick type (writing / piano / painting / reading / puzzle)
- For writing/reading: markdown text body
- For painting/piano: file upload + optional caption
- For puzzle: text body (could be a puzzle they solved or a puzzle they want to share)
- Post

### `/block` — Block management
Shows current block info (week N of M, days remaining), with:
- Mid-block review button (active in week 4 ±3 days)
- End-block review button (active in last week)
- Block history list

### `/block/review/mid` — Mid-block review
A guided form per user:
- For each measurable goal: how's pace? Want to amend the target?
- For each binary goal: any progress notes?
- For habits: anything to drop, add, or change frequency on?
- Free text: "what's working, what isn't"

Submitting marks `mid_review_done_at`. Both users do this independently.

### `/block/review/end` — End-of-block review
- For each goal: mark final status (hit / partially_hit / missed / abandoned), add resolution note
- Free text reflection
- "Start next block" button — opens a setup flow that pre-fills habits and lets the user pick carry-over goals

### `/settings`
- Display name
- Avatar initial
- Timezone (IANA, e.g. `Europe/Amsterdam`)
- Password change
- Block length default

---

## Cross-cutting behavior

### Timezones

Each user has a TZ. "Today" is computed in that user's local time. So when computing the dashboard, server fetches user A's today (in A's TZ) and user B's today (in B's TZ) — they may be different calendar dates and that's fine.

All timestamps stored as UTC. Conversions happen at the edges (input parsing, template rendering).

### Streaks and weekly %

- **Streak** = consecutive days where the user submitted a check-in with at least one habit marked `done`. Rest days do not break a streak (intentional rest is fine). Missed days do.
- **Weekly %** = of the daily-frequency habits, what fraction were done this week. Weekly-frequency habits contribute pro-rata (e.g. 5x/week habit done 3 times = 60%). Display rounded to nearest %.

Both are shown small and subtle. Not the main metric. No leaderboard, no comparison framing.

### Pace calculation

For measurable goals with non-trivial duration:
- Elapsed fraction = days elapsed in block / total block days
- Progress fraction = (current - start) / (target - start)
- If `progress_fraction >= elapsed_fraction - 0.05` → "on track" (info badge)
- Else → "behind pace" (warning badge), with note: "at current pace, finish in week X"
- Once past target → "hit" (success badge)

For binary goals with milestones: same logic, treating "milestones hit" as progress.

For binary goals without milestones: no pace badge.

### Notifications

Out of scope for v1. No emails, no push. Open-the-app accountability only.

---

## Data model summary

```
User(id, username, password_hash, display_name, color, avatar_initial, timezone, created_at)

Block(id, start_date, end_date, length_weeks, status, mid_review_done_at, end_review_done_at, created_at)

Goal(id, user_id, block_id, title, description, category, kind, status, resolution_note, created_at, amended_at, amendment_reason)
  - measurable goals: start_value, target_value, unit
  - binary goals: latest_result, last_attempt_at

GoalProgress(id, goal_id, value, logged_at, note)
GoalAttempt(id, goal_id, result, logged_at, note)
GoalMilestone(id, goal_id, position, label, value, hit_at)

Habit(id, user_id, block_id, name, icon, frequency, weekly_target, position, status, created_at, paused_at, ended_at, pause_reason)

CheckIn(id, user_id, date, note, submitted_at)
CheckInEntry(id, check_in_id, habit_id, state)
AdHocItem(id, check_in_id, text, done)

CreativePost(id, user_id, type, body, media_url, created_at)
Reaction(id, post_id, user_id, emoji, comment, created_at)

Session(id, user_id, created_at, expires_at)
```

Indexes:
- `CheckIn(user_id, date)` unique
- `Goal(block_id, user_id)`
- `Habit(block_id, user_id, status)`
- `CreativePost(created_at desc)`

---

## URL routes (FastAPI)

### Pages (HTML responses)
- `GET /login`, `POST /login`, `POST /logout`
- `GET /` — dashboard
- `GET /checkin`
- `GET /goals` (with `?user=me|other|both` query param)
- `GET /habits`
- `GET /feed`, `GET /feed/new`, `GET /feed/:id`
- `GET /block`, `GET /block/review/mid`, `GET /block/review/end`
- `GET /settings`

### HTMX fragments / mutations
- `POST /checkin/entry/:habit_id/cycle` — cycle state (returns updated row fragment)
- `POST /checkin/note` — save note
- `POST /checkin/adhoc` — add ad-hoc item
- `POST /checkin/adhoc/:id/toggle` — toggle done
- `DELETE /checkin/adhoc/:id` — remove
- `POST /habits` — create
- `PATCH /habits/:id` — update name/icon/frequency/position
- `POST /habits/:id/pause`, `POST /habits/:id/resume`, `POST /habits/:id/end`
- `POST /goals` — create
- `PATCH /goals/:id` — amend (with reason)
- `POST /goals/:id/progress` — log progress
- `POST /goals/:id/attempt` — log binary attempt
- `POST /goals/:id/resolve` — end-of-block resolution
- `POST /feed` — create post (multipart for uploads)
- `POST /feed/:id/react` — toggle reaction
- `POST /feed/:id/comment` — add comment
- `GET /uploads/:filename` — authenticated file serving

### Background
- A small APScheduler job at server start: every hour, for each user, check if their local day has rolled over; mark any pending entries from yesterday as missed once past the grace window.

---

## Design system

### Layout
- Mobile-first (the daily check-in is a phone-in-hand action), but desktop layout should be clean too
- Max content width on desktop: 720px for single-column screens, 960px for dashboard
- Generous whitespace; no shadows; flat surfaces; 0.5px borders

### Type
- Sans-serif system stack (Inter if available via system, else system fonts)
- Body 14–16px, headings 18–22px, weight 500 for emphasis (never 700)
- Sentence case throughout

### Color
- User A: blue family (light bg `#E6F1FB`, text/accent `#0C447C` to `#378ADD`)
- User B: pink family (light bg `#FBEAF0`, text/accent `#72243E` to `#D4537E`)
- Status: success (teal `#1D9E75`), warning (amber `#BA7517`), neutral (grays)
- Light + dark mode both supported via CSS variables

### Components
- Cards: white bg, 0.5px border, radius 12px, padding 1rem 1.25rem
- Buttons: outline style, transparent bg, hover bg-secondary
- Progress bars: 4–6px tall, color matches user
- Habit rows: 12px padding, icon + name + frequency hint + state
- Tabs: pill-style, light bg with darker active state

### Icons
- Tabler outline icon set (CDN). Examples: `ti-barbell`, `ti-pencil`, `ti-piano`, `ti-meat`, `ti-moon`, `ti-palette`, `ti-book`, `ti-puzzle`

---

## Deployment

### Container
Single Dockerfile. Python 3.12 slim base, install deps, copy app, run uvicorn. Static assets served by FastAPI under `/static`. Uploads served via authenticated route, not as static files.

### Fly.io
- One app, one machine (shared CPU, 256MB or 512MB RAM is plenty)
- One volume mounted at `/data`
  - `/data/db.sqlite` — the database
  - `/data/uploads/` — uploaded files
- Secrets: `SESSION_SECRET`, optional Litestream creds
- `fly.toml` with internal port 8000, http_service forcing HTTPS

### Backup
- Litestream as a sidecar process inside the same container, replicating `/data/db.sqlite` to S3-compatible storage continuously
- Volume snapshots from Fly as a second layer
- For files: a weekly cron tar+upload of `/data/uploads/`, or move to R2 later if it gets bigger than ~500MB

### Local dev
- `uvicorn app.main:app --reload`
- SQLite file in `./dev.db`, uploads in `./dev_uploads/`
- A `seed.py` script creates the two users with default passwords

---

## Out of scope for v1

Explicit list of things we discussed and chose to leave out:
- Email magic links, OAuth, password reset flows
- Notifications / reminders / nudges
- Numeric habit tracking (minutes, reps) — binary only
- Goal weights / priorities
- Nested sub-goals (milestones cover sub-steps)
- Habit templates / packs
- Streak gamification (badges, levels, etc.)
- Leaderboard or competitive framing
- Mobile app — responsive web only
- Comments on check-ins
- Editing past check-ins beyond the grace window
- Shared goals (only individual goals + shared block)
- Multi-block visualization / long-term graphs (might come in v2)

---

## Build order (suggested)

1. Project skeleton: FastAPI app, SQLAlchemy setup, Alembic, Jinja, Tailwind via CDN, base layout
2. Auth: login page, password verification, session cookie, login_required dependency
3. Seed script: create two users
4. Models + migrations: all tables
5. Habits CRUD + habits page
6. CheckIn flow + checkin page (the core daily loop)
7. Dashboard side-by-side
8. Goals CRUD + goals page (measurable first, then binary, then milestones)
9. Creative feed + composer + uploads + reactions
10. Block management + mid/end review flows
11. Timezone handling + day rollover background job
12. Litestream + Fly deploy
13. Polish pass: empty states, error messages, dark mode

Each step should ship in a usable state — don't build for two weeks then integrate.
