# Coaching Relationship Management System

A 1-coach-to-many-coachees system deployable on Wasmer Edge with MySQL.

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

## Local Development

```bash
# Create venv and install deps
python -m venv .env
source .env/bin/activate
pip install -r requirements.txt

# You need a local MySQL running. Set env vars:
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DB_USERNAME=root
export DB_PASSWORD=yourpassword
export DB_NAME=coaching

# Run
flask --app src/app run --debug --no-reload
```

Then visit http://127.0.0.1:5000/setup to create the coach account.

## Deploy to Wasmer Edge

```bash
# Install wasmer CLI: https://docs.wasmer.io/install
wasmer login

# Set up python venv for wasmer packaging
python -m venv .env
source .env/bin/activate
pip install -r requirements.txt

# Deploy (will auto-provision MySQL)
wasmer deploy
```

The app will be available at `https://coaching-system-<owner>.wasmer.app`.

Visit `/setup` on first deploy to create the coach account.

## Architecture

- **Backend**: Python / Flask
- **Database**: MySQL (auto-provisioned by Wasmer Edge)
- **Frontend**: Server-rendered HTML with Jinja2 templates
- **Deployment**: Wasmer Edge (WASI/WASIX Python runtime)

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
