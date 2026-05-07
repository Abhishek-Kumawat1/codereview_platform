# CodeReview Platform

A production-grade GitHub-integrated code review platform built with Python and Django.

## Live Features

- **GitHub OAuth login** — sign in with your GitHub account
- **Pull Request review cycles** — structured review workflow with multiple rounds
- **Real-time comments** — live updates via WebSockets (no page refresh)
- **AI pre-reviewer** — automatic PR analysis using Groq (Llama 3)
- **Async notifications** — email notifications via Celery task queue
- **GitHub Webhook integration** — PRs automatically appear when opened on GitHub
- **Role-based access control** — Author, Reviewer, Admin roles
- **REST API** — JWT-authenticated API endpoints

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5, Django REST Framework |
| Real-time | Django Channels, WebSockets, Daphne |
| Task queue | Celery, Redis |
| Database | PostgreSQL |
| Frontend | HTMX, Django Templates |
| Auth | GitHub OAuth (django-allauth), JWT |
| AI | Groq API (Llama 3) |
| Infrastructure | Docker Compose, Nginx, Gunicorn |

## Architecture

- **Multi-app Django monolith** with domain separation across
  `accounts`, `repositories`, `reviews`, and `notifications` apps
- **Split settings pattern** — `base/development/production`
  prevents accidental production misconfiguration
- **WebSocket consumers** broadcast live comments via Redis channel layer —
  all users viewing the same PR see new comments instantly
- **Celery task queue** decouples slow work (email, AI calls) from
  the HTTP request cycle — response time stays under 50ms regardless
  of how many notifications need sending
- **GitHub Webhook integration** with HMAC-SHA256 signature validation —
  PR events automatically create review cycles and trigger AI pre-review
- **AI pre-reviewer** fetches the PR diff from GitHub, sends it to
  Groq's Llama 3 model, parses structured JSON feedback, and broadcasts
  comments live via WebSocket

## Running Locally

```bash
# 1. Clone the repo
git clone https://github.com/xorb77/codereview-platform.git
cd codereview-platform

# 2. Set up environment variables
cp .env.example .env
# Edit .env and fill in your secrets (see Environment Variables below)

# 3. Start the full stack
docker compose up --build

# 4. Visit http://localhost
# Sign in with GitHub OAuth
```

## Environment Variables

See `.env.example` for all required variables. Key ones:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key — generate with `python -c "import secrets; print(secrets.token_hex(50))"` |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret |
| `GITHUB_TOKEN` | GitHub Personal Access Token (repo scope) |
| `GROQ_API_KEY` | Groq API key for AI pre-reviewer |

## Services

```
docker compose up starts 7 containers:

nginx     → port 80   — reverse proxy, static files, WS routing
django    → port 8000 — HTTP requests via Gunicorn
daphne    → port 8001 — WebSocket connections via ASGI
celery    → no port   — background task worker
db        → port 5432 — PostgreSQL
redis     → port 6379 — Celery broker + WebSocket channel layer
mailpit   → port 8025 — Email UI (development only)
```

## API Endpoints

```
GET  /api/reviews/          — list PRs for authenticated user
GET  /api/reviews/<pk>/     — PR detail with cycles and comments
GET  /api/cycles/<pk>/      — review cycle detail
GET  /api/stats/            — dashboard statistics
POST /accounts/api/token/   — obtain JWT token pair
POST /accounts/api/token/refresh/ — refresh JWT token
```

## Key Design Decisions

**HTMX over React** — kept the stack cohesive and eliminated a separate
frontend build pipeline. Delivers dynamic partial-page interactions
with server-side rendering benefits. The entire frontend is Django
templates + HTMX attributes — no npm, no build tools, no JavaScript framework.

**Celery for notifications** — email sending via SMTP takes 300ms-2s.
Blocking the HTTP request cycle for this would make every review submission
feel slow. Celery decouples it — the user gets a response in ~25ms,
emails are delivered seconds later in a background worker.

**WebSockets only for comments** — WebSockets add complexity so they're
used only where real-time genuinely matters. Comment feeds need
sub-second updates. Everything else (form submissions, status updates)
uses HTMX over standard HTTP.

**Custom User model from day one** — changing `AUTH_USER_MODEL` after
the first migration requires dropping and recreating the database.
Defining a custom model at project start (even if it initially adds
nothing) is a best practice that costs nothing upfront and saves
significant pain later.

## Project Structure

```
codereview/
├── config/                  # Django project config
│   ├── settings/
│   │   ├── base.py          # shared settings
│   │   ├── development.py   # local overrides
│   │   └── production.py    # production overrides
│   ├── asgi.py              # ASGI entry point (Daphne + Channels)
│   ├── wsgi.py              # WSGI entry point (Gunicorn)
│   ├── urls.py              # root URL router
│   ├── routing.py           # WebSocket URL router
│   └── celery.py            # Celery app instance
│
├── apps/
│   ├── accounts/            # User model, auth, roles, JWT
│   ├── repositories/        # GitHub repos, webhook receiver
│   ├── reviews/             # PRs, cycles, comments, consumers
│   └── notifications/       # Celery tasks, email, in-app notifs
│
├── templates/               # HTMX-powered Django templates
├── static/                  # CSS, JS
├── nginx/nginx.conf          # Nginx configuration
├── Dockerfile
└── docker-compose.yml
```

## Author

Built by [@xorb77](https://github.com/xorb77)