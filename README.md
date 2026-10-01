# DSCoaching — Coaching Relationship Management System

A 1-coach-to-many-coachees system deployed on Docker (ecb.pm) with PostgreSQL.

## Features

- **Coach dashboard**: overview of all coachees, compliance, pending tasks
- **Coachee dashboard**: check-ins, tasks, tracking, notes, mental conditioning
- **Bulk task assignment**: create once, assign to multiple coachees
- **Per-coachee customization**: individual contracts, boundaries, safe words
- **Immutable check-in log**: morning, evening, weekly — append-only, timestamped
- **Mental conditioning**: daily prompts (shared or per-coachee)
- **Acknowledgement system**: positive/negative from predefined categories
- **Safe word / pause**: coachee can trigger pause or full stop
- **Tracking**: food, hydration, alcohol, exercise, emotional regulation
- **Notes**: async bidirectional communication
- **Feature flags**: 10 toggleable features per coach/coachee
- **i18n**: English and French (session-based)

## Local Development

```bash
# SQLite (no external DB needed)
export DB_ENGINE=sqlite SECRET_KEY=dev
flask --app src/app run --debug --no-reload
```

Then visit http://127.0.0.1:5000/setup to create the coach account.

```bash
# Or with PostgreSQL via Docker Compose
docker-compose up
# Visit http://localhost:8080
```

## Production

Deployed at `https://dscoaching.ecb.pm/` — Docker container on ecb.pm behind Caddy, backed by PostgreSQL 16.

```bash
# Automated: push to main → CI quality gates → manual approval → SSH deploy
git push origin main

# Manual deploy: see devdocs/deployment.md
```

## Architecture

- **Backend**: Python 3.12 / Flask 3.1.3
- **Database**: PostgreSQL 16 (production), SQLite (tests)
- **Frontend**: Server-rendered HTML with Jinja2 templates
- **Deployment**: Docker on ecb.pm, Caddy reverse proxy, CI via GitHub Actions

## Data Model

- `coach` — the authority figure
- `coachee` — individuals being coached (each linked to a coach)
- `task_template` — reusable task definitions
- `task_assignment` — links tasks to coachees with status tracking
- `checkin` — immutable morning/evening/weekly entries
- `acknowledgement` — positive/negative logged per coachee
- `tracking_log` — food/hydration/alcohol/exercise/emotional entries
- `note` — async bidirectional communication
- `mental_conditioning` — daily prompts (shared or individual)
- `mental_conditioning_response` — coachee responses to prompts
